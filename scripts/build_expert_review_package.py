"""Build a self-contained review package for an external music expert."""

from __future__ import annotations

import argparse
import csv
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLE = (
    PROJECT_ROOT / "data" / "labels" / "omr_ground_truth_sample_thesis.csv"
)
DEFAULT_MIDI_DIR = PROJECT_ROOT / "outputs" / "midi"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "expert_review_package"
DEFAULT_AUDIO_FORMAT = "mp3"
KNOWN_MUSESCORE_PATHS = (
    Path(r"C:\Program Files\MuseScore 4\bin\MuseScore4.exe"),
    Path(r"C:\Program Files\MuseScore 4\bin\MuseScore4.com"),
    Path(r"C:\Program Files\MuseScore 3\bin\MuseScore3.exe"),
)
KNOWN_SOUNDFONT_PATHS = (
    Path(r"C:\Program Files\MuseScore 4\sound\MuseScore_General.sf3"),
    Path(r"C:\Program Files\MuseScore 4\share\sound\MuseScore_General.sf3"),
    Path(r"C:\Program Files\MuseScore 3\sound\MuseScore_General.sf3"),
)

REQUIRED_COLUMNS = {"doc_id", "page_index", "image_path"}
REVIEW_COLUMNS = [
    "doc_id",
    "page_index",
    "tracks_count",
    "usable",
    "pitch_quality",
    "duration_quality",
    "overall_quality",
    "comment",
]


def resolve_project_path(path_value: str, project_root: Path) -> Path:
    """Resolve a path stored in a project CSV."""
    path = Path(path_value)
    return path if path.is_absolute() else project_root / path


def build_midi_path(doc_id: str, page_index: int, midi_dir: Path) -> Path:
    """Build the expected MIDI path for one page."""
    return midi_dir / doc_id / f"page_{page_index:03d}.mid"


def build_page_directory(
    output_dir: Path,
    doc_id: str,
    page_index: int,
) -> Path:
    """Build the package directory for one reviewed page."""
    return output_dir / doc_id / f"page_{page_index:03d}"


def _find_executable(
    explicit_path: Path | None,
    command_names: tuple[str, ...],
    known_paths: tuple[Path, ...] = (),
) -> Path | None:
    if explicit_path is not None:
        if explicit_path.is_file():
            return explicit_path
        raise FileNotFoundError(f"Executable does not exist: {explicit_path}")
    for command_name in command_names:
        found = shutil.which(command_name)
        if found:
            return Path(found)
    for known_path in known_paths:
        if known_path.is_file():
            return known_path
    return None


def _find_soundfont(explicit_path: Path | None) -> Path | None:
    if explicit_path is not None:
        if explicit_path.is_file():
            return explicit_path
        raise FileNotFoundError(f"SoundFont does not exist: {explicit_path}")
    for known_path in KNOWN_SOUNDFONT_PATHS:
        if known_path.is_file():
            return known_path
    return None


def discover_audio_backend(
    *,
    musescore_bin: Path | None = None,
    ffmpeg_bin: Path | None = None,
    fluidsynth_bin: Path | None = None,
    soundfont: Path | None = None,
) -> dict[str, Path | str]:
    """Select MuseScore first, then FluidSynth plus ffmpeg."""
    musescore = _find_executable(
        musescore_bin,
        ("MuseScore4", "musescore", "mscore"),
        KNOWN_MUSESCORE_PATHS,
    )
    if musescore is not None:
        return {"name": "musescore", "musescore_bin": musescore}

    ffmpeg = _find_executable(ffmpeg_bin, ("ffmpeg",))
    fluidsynth = _find_executable(fluidsynth_bin, ("fluidsynth",))
    selected_soundfont = _find_soundfont(soundfont)
    if (
        ffmpeg is not None
        and fluidsynth is not None
        and selected_soundfont is not None
    ):
        return {
            "name": "fluidsynth_ffmpeg",
            "ffmpeg_bin": ffmpeg,
            "fluidsynth_bin": fluidsynth,
            "soundfont": selected_soundfont,
        }

    missing: list[str] = []
    if fluidsynth is None:
        missing.append("FluidSynth")
    if ffmpeg is None:
        missing.append("ffmpeg")
    if selected_soundfont is None:
        missing.append("SoundFont (.sf2/.sf3)")
    missing_text = ", ".join(missing)
    raise RuntimeError(
        "MIDI to MP3 backend is unavailable. Install MuseScore with CLI "
        "support, or install FluidSynth and ffmpeg and provide a SoundFont. "
        "You can pass --musescore-bin, or --fluidsynth-bin, --ffmpeg-bin "
        f"and --soundfont. Missing: {missing_text}."
    )


def _run_conversion_command(command: list[str], backend_name: str) -> None:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as error:
        raise RuntimeError(
            f"Could not start audio backend {backend_name}: {error}"
        ) from error
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(
            f"Audio backend {backend_name} exited with code "
            f"{completed.returncode}: {details}"
        )


def convert_midi_to_audio(
    midi_path: Path,
    audio_path: Path,
    backend: dict[str, Path | str],
    *,
    audio_format: str = DEFAULT_AUDIO_FORMAT,
) -> None:
    """Convert one MIDI file to MP3 through the selected local backend."""
    if audio_format != "mp3":
        raise ValueError(f"Unsupported audio format: {audio_format}")
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    backend_name = str(backend["name"])

    if backend_name == "musescore":
        _run_conversion_command(
            [
                str(backend["musescore_bin"]),
                "-o",
                str(audio_path),
                str(midi_path),
            ],
            backend_name,
        )
    elif backend_name == "fluidsynth_ffmpeg":
        wav_path = audio_path.with_suffix(".wav")
        try:
            _run_conversion_command(
                [
                    str(backend["fluidsynth_bin"]),
                    "-ni",
                    str(backend["soundfont"]),
                    str(midi_path),
                    "-F",
                    str(wav_path),
                    "-r",
                    "44100",
                ],
                "fluidsynth",
            )
            _run_conversion_command(
                [
                    str(backend["ffmpeg_bin"]),
                    "-y",
                    "-i",
                    str(wav_path),
                    "-codec:a",
                    "libmp3lame",
                    "-q:a",
                    "2",
                    str(audio_path),
                ],
                "ffmpeg",
            )
        finally:
            wav_path.unlink(missing_ok=True)
    else:
        raise ValueError(f"Unknown audio backend: {backend_name}")

    if not audio_path.is_file() or audio_path.stat().st_size == 0:
        raise RuntimeError(
            f"Audio backend {backend_name} did not create MP3: {audio_path}"
        )


def _read_variable_length(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        if offset >= len(data):
            raise ValueError("Unexpected end of MIDI variable-length value.")
        byte = data[offset]
        offset += 1
        value = (value << 7) | (byte & 0x7F)
        if byte < 0x80:
            return value, offset
    raise ValueError("Invalid MIDI variable-length value.")


def _track_has_notes(track_data: bytes) -> bool:
    """Return whether a raw MIDI track contains an audible note-on event."""
    offset = 0
    running_status: int | None = None

    while offset < len(track_data):
        _, offset = _read_variable_length(track_data, offset)
        if offset >= len(track_data):
            raise ValueError("MIDI event is missing a status byte.")

        if track_data[offset] >= 0x80:
            status = track_data[offset]
            offset += 1
            if status < 0xF0:
                running_status = status
        elif running_status is not None:
            status = running_status
        else:
            raise ValueError("MIDI running status has no preceding status byte.")

        if status == 0xFF:
            if offset >= len(track_data):
                raise ValueError("Incomplete MIDI meta event.")
            offset += 1
            length, offset = _read_variable_length(track_data, offset)
            offset += length
            if offset > len(track_data):
                raise ValueError("MIDI meta event exceeds track length.")
            continue

        if status in (0xF0, 0xF7):
            length, offset = _read_variable_length(track_data, offset)
            offset += length
            if offset > len(track_data):
                raise ValueError("MIDI SysEx event exceeds track length.")
            continue

        message_type = status & 0xF0
        data_length = 1 if message_type in (0xC0, 0xD0) else 2
        if offset + data_length > len(track_data):
            raise ValueError("MIDI channel event exceeds track length.")
        event_data = track_data[offset : offset + data_length]
        offset += data_length
        if message_type == 0x90 and event_data[1] > 0:
            return True

    return False


def _read_midi_chunks(midi_path: Path) -> tuple[bytes, list[bytes]]:
    data = midi_path.read_bytes()
    if len(data) < 14 or data[:4] != b"MThd":
        raise ValueError(f"Not a Standard MIDI file: {midi_path}")

    header_length = struct.unpack(">I", data[4:8])[0]
    header_end = 8 + header_length
    if header_length < 6 or header_end > len(data):
        raise ValueError(f"Invalid MIDI header: {midi_path}")
    header = data[8:header_end]
    expected_tracks = struct.unpack(">H", header[2:4])[0]

    tracks: list[bytes] = []
    offset = header_end
    for _ in range(expected_tracks):
        if offset + 8 > len(data) or data[offset : offset + 4] != b"MTrk":
            raise ValueError(f"Invalid MIDI track chunk: {midi_path}")
        track_length = struct.unpack(">I", data[offset + 4 : offset + 8])[0]
        track_start = offset + 8
        track_end = track_start + track_length
        if track_end > len(data):
            raise ValueError(f"Truncated MIDI track: {midi_path}")
        tracks.append(data[track_start:track_end])
        offset = track_end
    return header, tracks


def _write_midi(
    output_path: Path,
    header: bytes,
    tracks: list[bytes],
) -> None:
    updated_header = bytearray(header)
    updated_header[0:2] = struct.pack(">H", 1 if len(tracks) > 1 else 0)
    updated_header[2:4] = struct.pack(">H", len(tracks))

    with output_path.open("wb") as destination:
        destination.write(b"MThd")
        destination.write(struct.pack(">I", len(updated_header)))
        destination.write(updated_header)
        for track in tracks:
            destination.write(b"MTrk")
            destination.write(struct.pack(">I", len(track)))
            destination.write(track)


def split_midi_tracks(midi_path: Path, output_dir: Path) -> list[Path]:
    """Create one temporary MIDI per musical track.

    Tracks without note-on events are retained because they commonly contain
    tempo, meter, key signature, or other conductor metadata. A single-part
    MIDI is copied unchanged as track 1.
    """
    header, tracks = _read_midi_chunks(midi_path)
    musical_indexes = [
        index for index, track in enumerate(tracks) if _track_has_notes(track)
    ]
    output_dir.mkdir(parents=True, exist_ok=True)

    if len(musical_indexes) <= 1:
        output_path = output_dir / "track_01.mid"
        shutil.copy2(midi_path, output_path)
        return [output_path]

    metadata_tracks = [
        track for index, track in enumerate(tracks) if index not in musical_indexes
    ]
    output_paths: list[Path] = []
    for track_number, track_index in enumerate(musical_indexes, start=1):
        output_path = output_dir / f"track_{track_number:02d}.mid"
        _write_midi(
            output_path,
            header,
            [*metadata_tracks, tracks[track_index]],
        )
        output_paths.append(output_path)
    return output_paths


def read_sample_rows(sample_path: Path) -> list[dict[str, str]]:
    """Read and validate the ground-truth sample CSV."""
    if not sample_path.is_file():
        raise FileNotFoundError(f"Ground-truth sample does not exist: {sample_path}")
    with sample_path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS.difference(columns)
        if missing:
            names = ", ".join(sorted(missing))
            raise ValueError(
                f"Ground-truth sample is missing required columns: {names}"
            )
        rows = list(reader)
    if not rows:
        raise ValueError(f"Ground-truth sample contains no rows: {sample_path}")
    return rows


def prepare_package_rows(
    rows: list[dict[str, str]],
    *,
    output_dir: Path,
    midi_dir: Path,
    project_root: Path,
) -> list[dict[str, object]]:
    """Resolve every input and reject incomplete or duplicate samples."""
    prepared: list[dict[str, object]] = []
    seen: set[tuple[str, int]] = set()
    missing_files: list[str] = []

    for row in rows:
        doc_id = row["doc_id"].strip()
        if not doc_id:
            raise ValueError("Ground-truth sample contains an empty doc_id.")
        try:
            page_index = int(row["page_index"])
        except ValueError as error:
            raise ValueError(
                f"Invalid page_index for {doc_id}: {row['page_index']!r}"
            ) from error
        if page_index <= 0:
            raise ValueError(
                f"page_index must be positive for {doc_id}: {page_index}"
            )

        key = (doc_id, page_index)
        if key in seen:
            raise ValueError(
                f"Duplicate page in ground-truth sample: "
                f"{doc_id}/page_{page_index:03d}"
            )
        seen.add(key)

        scan_source = resolve_project_path(row["image_path"], project_root)
        midi_source = build_midi_path(doc_id, page_index, midi_dir)
        package_midi = (
            build_page_directory(output_dir, doc_id, page_index) / "midi.mid"
        )
        if not midi_source.is_file() and package_midi.is_file():
            midi_source = package_midi
        if not scan_source.is_file():
            missing_files.append(f"scan: {scan_source}")
        if not midi_source.is_file():
            missing_files.append(f"MIDI: {midi_source}")

        page_dir = build_page_directory(output_dir, doc_id, page_index)
        prepared.append(
            {
                "doc_id": doc_id,
                "page_index": page_index,
                "scan_source": scan_source,
                "midi_source": midi_source,
                "page_dir": page_dir,
            }
        )

    if missing_files:
        preview = "\n".join(f"- {item}" for item in missing_files[:10])
        remainder = len(missing_files) - 10
        if remainder > 0:
            preview += f"\n- ... and {remainder} more"
        raise FileNotFoundError(
            "Expert package inputs are incomplete:\n" + preview
        )
    return prepared


def build_readme(page_count: int, audio_format: str = DEFAULT_AUDIO_FORMAT) -> str:
    """Return the Russian instruction included in the package."""
    return f"""# Пакет экспертной проверки NoteVision OMR

Пакет содержит **{page_count} страниц** для внешней музыкальной экспертизы.

## Содержимое

Для каждой страницы создан отдельный каталог:

```text
<doc_id>/page_XXX/
  scan.png
  audio.{audio_format}
  midi.mid
  tracks/
    track_01.{audio_format}
    track_02.{audio_format}
    ...
```

`audio.{audio_format}` содержит общий результат со всеми партиями.
`tracks/track_XX.{audio_format}` содержит отдельные MIDI-дорожки или партии.
Если MIDI содержит одну музыкальную дорожку, создаётся только
`tracks/track_01.{audio_format}`.

Файл `expert_review.csv` содержит по одной строке на страницу. Заполнять нужно
только поля оценки и комментарий. Колонка `tracks_count` показывает количество
отдельных аудиодорожек. `doc_id`, `page_index` и `tracks_count` изменять не
следует.

## Порядок проверки

1. Откройте `scan.png` и изучите исходную нотную страницу.
2. Прослушайте `audio.{audio_format}` на телефоне или компьютере.
3. При необходимости прослушайте отдельные партии в каталоге `tracks`.
4. Сравните мелодию, высоты нот и ритм аудио с исходным сканом.
5. Заполните соответствующую строку в `expert_review.csv`.
6. При заметных ошибках кратко опишите их в поле `comment`.

MIDI-файл `midi.mid` оставлен дополнительно. Для обычной проверки его можно
игнорировать.

## Поля оценки

### `usable`

- `yes` — результат можно использовать почти без правок;
- `partial` — результат можно использовать после ручной корректировки;
- `no` — результат непригоден.

### `pitch_quality`

Оценка высоты нот от 1 до 5:

- `5` — почти без ошибок;
- `3` — есть заметные ошибки, но мелодия узнаваема;
- `1` — высоты нот в основном неверные.

### `duration_quality`

Оценка длительностей и ритма от 1 до 5:

- `5` — ритм в основном совпадает;
- `3` — есть ошибки длительностей;
- `1` — ритм существенно нарушен.

### `overall_quality`

Общая оценка от 1 до 5:

- `5` — результат пригоден для дальнейшей работы;
- `3` — результат частично пригоден;
- `1` — результат непригоден.

Промежуточные значения `2` и `4` можно использовать, если качество находится
между описанными уровнями.

### `comment`

Краткий комментарий о характерных ошибках: неверные ноты, сбитый ритм,
пропуски, лишние события, проблемы отдельных голосов или другие наблюдения.

## Важно

- Не переименовывайте каталоги и файлы.
- Не меняйте значения `doc_id`, `page_index` и `tracks_count`.
- Если `audio.{audio_format}` не открывается или не воспроизводится, укажите
  `usable=no` и опишите проблему.
- Оценка должна отражать музыкальную пригодность результата, а не только факт
  успешного открытия аудиофайла.
"""


def write_review_csv(
    output_path: Path,
    prepared_rows: list[dict[str, object]],
) -> None:
    """Write an empty expert review template."""
    with output_path.open("w", encoding="utf-8-sig", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        for row in prepared_rows:
            writer.writerow(
                {
                    "doc_id": row["doc_id"],
                    "page_index": row["page_index"],
                    "tracks_count": row["tracks_count"],
                    "usable": "",
                    "pitch_quality": "",
                    "duration_quality": "",
                    "overall_quality": "",
                    "comment": "",
                }
            )


def build_expert_review_package(
    sample_path: Path,
    output_dir: Path,
    *,
    midi_dir: Path = DEFAULT_MIDI_DIR,
    project_root: Path = PROJECT_ROOT,
    overwrite: bool = False,
    audio_format: str = DEFAULT_AUDIO_FORMAT,
    musescore_bin: Path | None = None,
    ffmpeg_bin: Path | None = None,
    fluidsynth_bin: Path | None = None,
    soundfont: Path | None = None,
    audio_backend: dict[str, Path | str] | None = None,
    audio_converter: Callable[..., None] = convert_midi_to_audio,
    track_splitter: Callable[[Path, Path], list[Path]] = split_midi_tracks,
) -> dict[str, object]:
    """Copy review artifacts and create the CSV template and README."""
    if audio_format != "mp3":
        raise ValueError(
            f"Unsupported audio format: {audio_format}. Only mp3 is supported."
        )
    rows = read_sample_rows(sample_path)
    prepared = prepare_package_rows(
        rows,
        output_dir=output_dir,
        midi_dir=midi_dir,
        project_root=project_root,
    )

    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise FileExistsError(
            f"Output directory is not empty: {output_dir}. "
            "Use --overwrite to replace package files."
        )

    backend = audio_backend or discover_audio_backend(
        musescore_bin=musescore_bin,
        ffmpeg_bin=ffmpeg_bin,
        fluidsynth_bin=fluidsynth_bin,
        soundfont=soundfont,
    )

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{output_dir.name}-",
        dir=output_dir.parent,
    ) as temporary_dir:
        staged_package = Path(temporary_dir) / output_dir.name
        staged_rows: list[dict[str, object]] = []
        track_audio_files = 0
        for row in prepared:
            page_dir = build_page_directory(
                staged_package,
                str(row["doc_id"]),
                int(row["page_index"]),
            )
            page_dir.mkdir(parents=True, exist_ok=True)
            staged_midi = page_dir / "midi.mid"
            shutil.copy2(Path(row["scan_source"]), page_dir / "scan.png")
            shutil.copy2(Path(row["midi_source"]), staged_midi)
            audio_converter(
                staged_midi,
                page_dir / f"audio.{audio_format}",
                backend,
                audio_format=audio_format,
            )
            tracks_dir = page_dir / "tracks"
            tracks_dir.mkdir()
            with tempfile.TemporaryDirectory(
                prefix=".track-midi-",
                dir=page_dir,
            ) as track_midi_dir:
                split_midis = track_splitter(
                    staged_midi,
                    Path(track_midi_dir),
                )
                if not split_midis:
                    raise RuntimeError(
                        f"No MIDI tracks were produced for {staged_midi}"
                    )
                for track_number, track_midi in enumerate(
                    split_midis,
                    start=1,
                ):
                    audio_converter(
                        track_midi,
                        tracks_dir
                        / f"track_{track_number:02d}.{audio_format}",
                        backend,
                        audio_format=audio_format,
                    )
            tracks_count = len(split_midis)
            track_audio_files += tracks_count
            staged_rows.append(
                {
                    **row,
                    "page_dir": page_dir,
                    "tracks_count": tracks_count,
                }
            )

        review_path = staged_package / "expert_review.csv"
        readme_path = staged_package / "README.md"
        write_review_csv(review_path, staged_rows)
        readme_path.write_text(
            build_readme(len(staged_rows), audio_format),
            encoding="utf-8",
        )

        if output_dir.exists():
            shutil.rmtree(output_dir)
        shutil.move(str(staged_package), str(output_dir))

    return {
        "pages": len(prepared),
        "scan_files": len(prepared),
        "audio_files": len(prepared),
        "track_audio_files": track_audio_files,
        "midi_files": len(prepared),
        "audio_format": audio_format,
        "audio_backend": backend["name"],
        "review_csv": output_dir / "expert_review.csv",
        "readme": output_dir / "README.md",
        "output_dir": output_dir,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--midi-dir", type=Path, default=DEFAULT_MIDI_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--audio-format",
        choices=["mp3"],
        default=DEFAULT_AUDIO_FORMAT,
    )
    parser.add_argument("--musescore-bin", type=Path)
    parser.add_argument("--ffmpeg-bin", type=Path)
    parser.add_argument("--fluidsynth-bin", type=Path)
    parser.add_argument("--soundfont", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        summary = build_expert_review_package(
            args.sample,
            args.out_dir,
            midi_dir=args.midi_dir,
            overwrite=args.overwrite,
            audio_format=args.audio_format,
            musescore_bin=args.musescore_bin,
            ffmpeg_bin=args.ffmpeg_bin,
            fluidsynth_bin=args.fluidsynth_bin,
            soundfont=args.soundfont,
        )
    except (
        FileNotFoundError,
        FileExistsError,
        RuntimeError,
        ValueError,
        OSError,
    ) as error:
        raise SystemExit(f"Error: {error}") from error

    print(f"Pages: {summary['pages']}")
    print(f"Scans copied: {summary['scan_files']}")
    print(f"Audio created: {summary['audio_files']}")
    print(f"Track audio created: {summary['track_audio_files']}")
    print(f"MIDI copied: {summary['midi_files']}")
    print(f"Audio backend: {summary['audio_backend']}")
    print(f"Review CSV: {summary['review_csv']}")
    print(f"README: {summary['readme']}")
    print(f"Package: {summary['output_dir']}")


if __name__ == "__main__":
    main()
