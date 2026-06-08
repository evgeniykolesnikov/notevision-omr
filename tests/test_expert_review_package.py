"""Tests for the external expert review package builder."""

import csv
import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "build_expert_review_package.py"
SPEC = importlib.util.spec_from_file_location(
    "build_expert_review_package",
    SCRIPT_PATH,
)
assert SPEC is not None and SPEC.loader is not None
package = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package)


def write_sample(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(
            destination,
            fieldnames=["doc_id", "page_index", "image_path"],
        )
        writer.writeheader()
        writer.writerows(rows)


def write_midi(path: Path, musical_tracks: int = 1) -> None:
    tracks: list[bytes] = []
    if musical_tracks > 1:
        tracks.append(b"\x00\xff\x51\x03\x07\xa1\x20\x00\xff\x2f\x00")
    for index in range(musical_tracks):
        channel = index % 16
        tracks.append(
            bytes(
                [
                    0x00,
                    0x90 | channel,
                    0x3C + index,
                    0x40,
                    0x60,
                    0x80 | channel,
                    0x3C + index,
                    0x40,
                    0x00,
                    0xFF,
                    0x2F,
                    0x00,
                ]
            )
        )
    format_type = 1 if len(tracks) > 1 else 0
    with path.open("wb") as destination:
        destination.write(b"MThd")
        destination.write(struct.pack(">IHHH", 6, format_type, len(tracks), 480))
        for track in tracks:
            destination.write(b"MTrk")
            destination.write(struct.pack(">I", len(track)))
            destination.write(track)


class ExpertReviewPackageTests(unittest.TestCase):
    def test_builds_page_files_review_csv_and_readme(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            sample_path = root / "sample.csv"
            scan = root / "outputs" / "pages" / "doc-a" / "page_002.png"
            midi = root / "outputs" / "midi" / "doc-a" / "page_002.mid"
            scan.parent.mkdir(parents=True)
            midi.parent.mkdir(parents=True)
            scan.write_bytes(b"scan")
            write_midi(midi)
            write_sample(
                sample_path,
                [
                    {
                        "doc_id": "doc-a",
                        "page_index": 2,
                        "image_path": "outputs/pages/doc-a/page_002.png",
                    }
                ],
            )

            output_dir = root / "package"

            def fake_audio_converter(
                midi_path: Path,
                audio_path: Path,
                backend: dict[str, object],
                *,
                audio_format: str,
            ) -> None:
                self.assertEqual(audio_format, "mp3")
                self.assertTrue(midi_path.is_file())
                audio_path.write_bytes(b"mp3")

            summary = package.build_expert_review_package(
                sample_path,
                output_dir,
                midi_dir=root / "outputs" / "midi",
                project_root=root,
                audio_backend={"name": "test"},
                audio_converter=fake_audio_converter,
            )

            page_dir = output_dir / "doc-a" / "page_002"
            self.assertEqual((page_dir / "scan.png").read_bytes(), b"scan")
            self.assertEqual((page_dir / "audio.mp3").read_bytes(), b"mp3")
            self.assertEqual(
                (page_dir / "midi.mid").read_bytes(),
                midi.read_bytes(),
            )
            self.assertTrue((page_dir / "tracks").is_dir())
            self.assertEqual(
                (page_dir / "tracks" / "track_01.mp3").read_bytes(),
                b"mp3",
            )
            self.assertTrue((output_dir / "README.md").is_file())
            self.assertEqual(summary["pages"], 1)
            self.assertEqual(summary["track_audio_files"], 1)

            with (output_dir / "expert_review.csv").open(
                encoding="utf-8-sig",
                newline="",
            ) as source:
                reader = csv.DictReader(source)
                rows = list(reader)
            self.assertEqual(reader.fieldnames, package.REVIEW_COLUMNS)
            self.assertEqual(rows[0]["doc_id"], "doc-a")
            self.assertEqual(rows[0]["page_index"], "2")
            self.assertEqual(rows[0]["tracks_count"], "1")
            self.assertEqual(rows[0]["usable"], "")

    def test_split_midi_tracks_exports_each_musical_track(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            midi = root / "multi.mid"
            write_midi(midi, musical_tracks=2)

            split_paths = package.split_midi_tracks(midi, root / "split")

            self.assertEqual(
                [path.name for path in split_paths],
                ["track_01.mid", "track_02.mid"],
            )
            for path in split_paths:
                _, tracks = package._read_midi_chunks(path)
                musical_count = sum(
                    package._track_has_notes(track) for track in tracks
                )
                self.assertEqual(musical_count, 1)

    def test_single_track_midi_uses_graceful_track_01_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            midi = root / "single.mid"
            write_midi(midi)

            split_paths = package.split_midi_tracks(midi, root / "split")

            self.assertEqual(len(split_paths), 1)
            self.assertEqual(split_paths[0].name, "track_01.mid")
            self.assertEqual(split_paths[0].read_bytes(), midi.read_bytes())

    def test_missing_midi_rejects_package_before_output_is_created(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            sample_path = root / "sample.csv"
            scan = root / "scan.png"
            scan.write_bytes(b"scan")
            write_sample(
                sample_path,
                [
                    {
                        "doc_id": "doc-a",
                        "page_index": 1,
                        "image_path": str(scan),
                    }
                ],
            )
            output_dir = root / "package"

            with self.assertRaisesRegex(FileNotFoundError, "MIDI"):
                package.build_expert_review_package(
                    sample_path,
                    output_dir,
                    midi_dir=root / "midi",
                    project_root=root,
                    audio_backend={"name": "test"},
                )

            self.assertFalse(output_dir.exists())

    def test_non_empty_output_requires_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            sample_path = root / "sample.csv"
            scan = root / "scan.png"
            midi = root / "midi" / "doc-a" / "page_001.mid"
            scan.write_bytes(b"scan")
            midi.parent.mkdir(parents=True)
            midi.write_bytes(b"midi")
            write_sample(
                sample_path,
                [
                    {
                        "doc_id": "doc-a",
                        "page_index": 1,
                        "image_path": str(scan),
                    }
                ],
            )
            output_dir = root / "package"
            output_dir.mkdir()
            (output_dir / "existing.txt").write_text("keep", encoding="utf-8")

            with self.assertRaisesRegex(FileExistsError, "--overwrite"):
                package.build_expert_review_package(
                    sample_path,
                    output_dir,
                    midi_dir=root / "midi",
                    project_root=root,
                    audio_backend={"name": "test"},
                )

    def test_readme_contains_rating_instructions(self) -> None:
        readme = package.build_readme(30)
        self.assertIn("30 страниц", readme)
        self.assertIn("pitch_quality", readme)
        self.assertIn("duration_quality", readme)
        self.assertIn("usable=no", readme)
        self.assertIn("audio.mp3", readme)
        self.assertIn("tracks/track_XX.mp3", readme)
        self.assertIn("одну музыкальную дорожку", readme)
        self.assertIn("MIDI", readme)
        self.assertIn("можно", readme)

    def test_missing_backend_returns_clear_error(self) -> None:
        with patch.object(package.shutil, "which", return_value=None), patch.object(
            package,
            "KNOWN_MUSESCORE_PATHS",
            (),
        ), patch.object(package, "KNOWN_SOUNDFONT_PATHS", ()):
            with self.assertRaisesRegex(
                RuntimeError,
                "Install MuseScore.*FluidSynth.*ffmpeg",
            ):
                package.discover_audio_backend()

    def test_musescore_backend_has_priority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            musescore = Path(temporary_dir) / "MuseScore4.exe"
            musescore.write_bytes(b"exe")
            backend = package.discover_audio_backend(
                musescore_bin=musescore,
            )
            self.assertEqual(backend["name"], "musescore")

    def test_audio_failure_preserves_existing_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            sample_path = root / "sample.csv"
            scan = root / "scan.png"
            midi = root / "midi" / "doc-a" / "page_001.mid"
            scan.write_bytes(b"scan")
            midi.parent.mkdir(parents=True)
            midi.write_bytes(b"midi")
            write_sample(
                sample_path,
                [
                    {
                        "doc_id": "doc-a",
                        "page_index": 1,
                        "image_path": str(scan),
                    }
                ],
            )
            output_dir = root / "package"
            output_dir.mkdir()
            marker = output_dir / "existing.txt"
            marker.write_text("keep", encoding="utf-8")

            def failing_converter(
                midi_path: Path,
                audio_path: Path,
                backend: dict[str, object],
                *,
                audio_format: str,
            ) -> None:
                raise RuntimeError("conversion failed")

            with self.assertRaisesRegex(RuntimeError, "conversion failed"):
                package.build_expert_review_package(
                    sample_path,
                    output_dir,
                    midi_dir=root / "midi",
                    project_root=root,
                    overwrite=True,
                    audio_backend={"name": "test"},
                    audio_converter=failing_converter,
                )

            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
