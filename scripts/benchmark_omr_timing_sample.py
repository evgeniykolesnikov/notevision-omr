"""Benchmark a tiny full OMR path sample without touching final VKR metrics.

The script selects music/mixed validated pages that do not already have
MXL/MusicXML artifacts, then runs only those selected pages through:
PNG -> Audiveris -> MXL/MusicXML -> MIDI -> music features.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from shutil import copy2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from analyze_music_features_unique_pages import (  # noqa: E402
    DEFAULT_ROOTS,
    DEFAULT_VALIDATED,
    find_artifacts,
    page_key,
    pct,
    read_validated_pages,
)
from notevision.music_features import extract_music_features  # noqa: E402

DEFAULT_SAMPLE_CSV = PROJECT_ROOT / "outputs" / "reports" / "omr_timing_sample_pages.csv"
DEFAULT_RAW_CSV = PROJECT_ROOT / "outputs" / "reports" / "omr_timing_sample_raw.csv"
DEFAULT_REPORT = PROJECT_ROOT / "outputs" / "reports" / "omr_timing_sample_report.md"
DEFAULT_NOTES = PROJECT_ROOT / "docs" / "thesis" / "local_vkr" / "omr_timing_sample_notes.md"
DEFAULT_OMR_DIR = PROJECT_ROOT / "outputs" / "omr_timing_sample"
DEFAULT_MIDI_DIR = PROJECT_ROOT / "outputs" / "midi_timing_sample"

SAMPLE_COLUMNS = [
    "doc_id",
    "page_index",
    "page_type",
    "png_path",
    "existing_mxl_found",
    "selected_for_timing",
]

RAW_COLUMNS = [
    "doc_id",
    "page_index",
    "page_type",
    "png_path",
    "page_preprocessing_ms",
    "audiveris_omr_ms",
    "mxl_created",
    "mxl_path",
    "midi_conversion_ms",
    "midi_created",
    "midi_path",
    "music_features_extraction_ms",
    "features_extracted",
    "total_ms",
    "error",
]


def rel(path: Path | str) -> str:
    path_obj = Path(path)
    try:
        return str(path_obj.resolve().relative_to(PROJECT_ROOT))
    except (OSError, ValueError):
        return str(path)


def resolve_project_path(value: object) -> Path:
    raw = str(value or "").strip().replace("\\", "/")
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def build_artifact_index(roots: list[Path]) -> dict[tuple[str, str], list[Path]]:
    index: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for artifact in find_artifacts(roots):
        if artifact.doc_id != "unknown" and artifact.page_index != "unknown":
            index[(artifact.doc_id, artifact.page_index)].append(artifact.path)
    return index


def select_sample(validated_rows: list[dict[str, str]], artifact_index: dict[tuple[str, str], list[Path]], sample_size: int) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    seen_docs: set[str] = set()
    deferred: list[dict[str, object]] = []
    for page in validated_rows:
        page_type = str(page.get("page_type", "")).strip().lower()
        if page_type not in {"music", "mixed"}:
            continue
        doc_id, page_index = page_key(str(page.get("doc_id", "")).strip(), page.get("page_index", ""))
        png_path = resolve_project_path(page.get("image_path", ""))
        if not png_path.is_file():
            continue
        if artifact_index.get((doc_id, page_index)):
            continue
        row = {
            "doc_id": doc_id,
            "page_index": page_index,
            "page_type": page_type,
            "png_path": rel(png_path),
            "existing_mxl_found": 0,
            "selected_for_timing": 1,
        }
        if doc_id not in seen_docs and len(candidates) < sample_size:
            candidates.append(row)
            seen_docs.add(doc_id)
        else:
            deferred.append(row)
        if len(candidates) >= sample_size:
            break
    for row in deferred:
        if len(candidates) >= sample_size:
            break
        candidates.append(row)
    return candidates


def write_csv(path: Path, rows: list[dict[str, object]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def preprocess_page(source_png: Path, work_png: Path) -> float:
    start = time.perf_counter()
    work_png.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image

        with Image.open(source_png) as image:
            image.convert("L").save(work_png)
    except Exception:
        copy2(source_png, work_png)
    return (time.perf_counter() - start) * 1000.0


def build_audiveris_command(input_path: Path, out_dir: Path, audiveris_bin: str) -> list[str]:
    return [
        audiveris_bin,
        "-batch",
        "-transcribe",
        "-export",
        "-output",
        str(out_dir),
        "--",
        str(input_path),
    ]


def find_created_mxl(out_dir: Path, input_path: Path, page_index: str) -> Path | None:
    patterns = []
    try:
        patterns.append(f"page_{int(float(page_index)):03d}*.mxl")
    except ValueError:
        pass
    patterns.append(f"{input_path.stem}*.mxl")
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(path for path in out_dir.rglob(pattern) if path.is_file())
    if not candidates:
        candidates.extend(path for path in out_dir.rglob("*.mxl") if path.is_file())
    return sorted(candidates, key=lambda path: str(path).lower())[0] if candidates else None


def run_audiveris(input_path: Path, out_dir: Path, audiveris_bin: str) -> tuple[float, Path | None, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    command = build_audiveris_command(input_path, out_dir, audiveris_bin)
    log_path = out_dir / f"{input_path.stem}_audiveris.log"
    start = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        duration_ms = (time.perf_counter() - start) * 1000.0
        log_path.write_text(
            "\n".join(
                [
                    f"Command: {subprocess.list2cmdline(command)}",
                    f"Return code: {completed.returncode}",
                    "",
                    "STDOUT",
                    completed.stdout or "",
                    "",
                    "STDERR",
                    completed.stderr or "",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        if completed.returncode != 0:
            return duration_ms, None, f"Audiveris exited with code {completed.returncode}; log={rel(log_path)}"
        return duration_ms, find_created_mxl(out_dir, input_path, input_path.stem), ""
    except FileNotFoundError:
        duration_ms = (time.perf_counter() - start) * 1000.0
        message = f"Audiveris executable was not found: {audiveris_bin}"
        log_path.write_text(message + "\n", encoding="utf-8")
        return duration_ms, None, message
    except OSError as error:
        duration_ms = (time.perf_counter() - start) * 1000.0
        message = f"Could not start Audiveris: {error}"
        log_path.write_text(message + "\n", encoding="utf-8")
        return duration_ms, None, message


def convert_mxl_to_midi(source_mxl: Path, midi_path: Path) -> tuple[float, bool, str]:
    start = time.perf_counter()
    try:
        from music21 import bar, converter, repeat

        midi_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            score = converter.parse(str(source_mxl))
            score.write("midi", fp=str(midi_path))
        except repeat.ExpanderException:
            score = converter.parse(str(source_mxl))
            for measure in score.recurse().getElementsByClass("Measure"):
                if isinstance(measure.leftBarline, bar.Repeat):
                    measure.leftBarline = None
                if isinstance(measure.rightBarline, bar.Repeat):
                    measure.rightBarline = None
            score.write("midi", fp=str(midi_path))
        return (time.perf_counter() - start) * 1000.0, midi_path.is_file(), ""
    except Exception as error:
        return (time.perf_counter() - start) * 1000.0, False, f"MIDI conversion failed: {error}"


def extract_features(source_mxl: Path) -> tuple[float, bool, str]:
    start = time.perf_counter()
    try:
        row = extract_music_features(source_mxl)
        status = str(row.get("extraction_status", ""))
        error = str(row.get("error", "") or "")
        return (time.perf_counter() - start) * 1000.0, status not in {"parse_error", "missing_file"}, error
    except Exception as error:
        return (time.perf_counter() - start) * 1000.0, False, f"Music features extraction failed: {error}"


def benchmark_sample(sample_rows: list[dict[str, object]], omr_dir: Path, midi_dir: Path, audiveris_bin: str) -> list[dict[str, object]]:
    raw_rows: list[dict[str, object]] = []
    for sample in sample_rows:
        doc_id = str(sample["doc_id"])
        page_index = str(sample["page_index"])
        page_name = f"page_{int(float(page_index)):03d}"
        source_png = resolve_project_path(sample["png_path"])
        page_omr_dir = omr_dir / doc_id / page_name
        work_png = page_omr_dir / f"{page_name}_timing_input.png"
        midi_path = midi_dir / doc_id / f"{page_name}.mid"
        total_start = time.perf_counter()
        errors: list[str] = []

        preprocessing_ms = preprocess_page(source_png, work_png)
        audiveris_ms, mxl_path, audiveris_error = run_audiveris(work_png, page_omr_dir, audiveris_bin)
        if audiveris_error:
            errors.append(audiveris_error)

        midi_ms = 0.0
        midi_created = False
        features_ms = 0.0
        features_extracted = False
        if mxl_path is not None and mxl_path.is_file():
            midi_ms, midi_created, midi_error = convert_mxl_to_midi(mxl_path, midi_path)
            if midi_error:
                errors.append(midi_error)
            features_ms, features_extracted, features_error = extract_features(mxl_path)
            if features_error:
                errors.append(features_error)

        total_ms = (time.perf_counter() - total_start) * 1000.0
        raw_rows.append(
            {
                "doc_id": doc_id,
                "page_index": page_index,
                "page_type": sample["page_type"],
                "png_path": sample["png_path"],
                "page_preprocessing_ms": round(preprocessing_ms, 3),
                "audiveris_omr_ms": round(audiveris_ms, 3),
                "mxl_created": int(mxl_path is not None and mxl_path.is_file()),
                "mxl_path": rel(mxl_path) if mxl_path else "",
                "midi_conversion_ms": round(midi_ms, 3),
                "midi_created": int(midi_created),
                "midi_path": rel(midi_path) if midi_created else "",
                "music_features_extraction_ms": round(features_ms, 3),
                "features_extracted": int(features_extracted),
                "total_ms": round(total_ms, 3),
                "error": " | ".join(errors),
            }
        )
    return raw_rows


def stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "median": 0.0, "min": 0.0, "max": 0.0}
    return {
        "mean": round(statistics.fmean(values), 3),
        "median": round(statistics.median(values), 3),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
    }


def summarize(raw_rows: list[dict[str, object]], remaining_count: int) -> dict[str, object]:
    successful_audiveris_rows = [row for row in raw_rows if int(row["mxl_created"])]
    midi_rows = [row for row in raw_rows if float(row["midi_conversion_ms"]) > 0]
    feature_rows = [row for row in raw_rows if float(row["music_features_extraction_ms"]) > 0]
    total_values = [float(row["total_ms"]) for row in raw_rows]
    total_stats = stats(total_values)
    return {
        "selected_pages": len(raw_rows),
        "audiveris_success": len(successful_audiveris_rows),
        "mxl_created": sum(int(row["mxl_created"]) for row in raw_rows),
        "midi_created": sum(int(row["midi_created"]) for row in raw_rows),
        "features_extracted": sum(int(row["features_extracted"]) for row in raw_rows),
        "preprocessing_stats": stats([float(row["page_preprocessing_ms"]) for row in raw_rows]),
        "audiveris_stats": stats([float(row["audiveris_omr_ms"]) for row in raw_rows]),
        "midi_stats": stats([float(row["midi_conversion_ms"]) for row in midi_rows]),
        "features_stats": stats([float(row["music_features_extraction_ms"]) for row in feature_rows]),
        "total_stats": total_stats,
        "remaining_count": remaining_count,
        "estimated_total_hours": round((remaining_count * float(total_stats["mean"])) / 1000.0 / 3600.0, 2),
    }


def stat_table(stage: str, values: dict[str, float]) -> str:
    return f"| {stage} | {values['mean']} | {values['median']} | {values['min']} | {values['max']} |"


def write_report(path: Path, summary: dict[str, object], raw_rows: list[dict[str, object]], sample_csv: Path, raw_csv: Path) -> None:
    lines = [
        "# OMR timing sample report",
        "",
        f"- Run timestamp: {datetime.now().isoformat(timespec='seconds')}",
        "- Scope: tiny sample of music/mixed pages without existing MXL/MusicXML.",
        "- Audiveris invoked: yes, sample only.",
        "- Final VKR metrics changed: no.",
        "",
        "## Summary",
        "",
        f"- Selected pages: {summary['selected_pages']}.",
        f"- Audiveris successful pages / MXL created: {summary['mxl_created']}.",
        f"- MIDI created: {summary['midi_created']}.",
        f"- Music features extracted: {summary['features_extracted']}.",
        "",
        "## Timing",
        "",
        "| stage | mean_ms | median_ms | min_ms | max_ms |",
        "|---|---:|---:|---:|---:|",
        stat_table("Page preprocessing", summary["preprocessing_stats"]),
        stat_table("Audiveris OMR", summary["audiveris_stats"]),
        stat_table("MIDI conversion", summary["midi_stats"]),
        stat_table("Music features extraction", summary["features_stats"]),
        stat_table("Total per page", summary["total_stats"]),
        "",
        "## Rough extrapolation",
        "",
        f"- remaining_music_mixed_without_mxl: {summary['remaining_count']}.",
        f"- estimated_total_time_hours: {summary['estimated_total_hours']}.",
        "- This is a rough estimate from a small sample and must not be treated as a final corpus runtime.",
        "",
        "## Per-page results",
        "",
        "| doc_id | page_index | page_type | mxl_created | midi_created | features_extracted | total_ms | error |",
        "|---|---:|---|---:|---:|---:|---:|---|",
    ]
    for row in raw_rows:
        error = str(row["error"]).replace("|", "/")
        lines.append(
            f"| {row['doc_id']} | {row['page_index']} | {row['page_type']} | {row['mxl_created']} | {row['midi_created']} | {row['features_extracted']} | {row['total_ms']} | {error} |"
        )
    lines.extend(
        [
            "",
            "## Defense wording",
            "",
            "> Music features are extracted from MXL/MusicXML, so pages without MXL require OMR first. A separate benchmark shows that preprocessing and feature extraction take milliseconds, while the main computational cost comes from Audiveris. A full run over all music/mixed pages is a separate batch task and was not mixed with final VKR metrics.",
            "",
            "## Outputs",
            "",
            f"- Sample pages: `{sample_csv.relative_to(PROJECT_ROOT)}`",
            f"- Raw timing: `{raw_csv.relative_to(PROJECT_ROOT)}`",
            "",
            "## Limitations",
            "",
            "- This is not OMR accuracy.",
            "- This is not musical correctness.",
            "- This does not mean all music pages were recognized.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_notes(path: Path, summary: dict[str, object], report_path: Path, raw_csv: Path, sample_csv: Path) -> None:
    text = f"""# omr_timing_sample_notes

DOCX VKR, defense PPTX/PDF and final VKR metrics were not changed. Git was not touched.

## Scope

- Audiveris was invoked only for the selected timing sample.
- Sample pages: {summary['selected_pages']}.
- Outputs were isolated under `outputs/omr_timing_sample/` and `outputs/midi_timing_sample/`.
- Existing OMR-300/fallback outputs were not overwritten.

## Results

- MXL created: {summary['mxl_created']}.
- MIDI created: {summary['midi_created']}.
- Music features extracted: {summary['features_extracted']}.
- Mean page preprocessing time: {summary['preprocessing_stats']['mean']} ms.
- Mean Audiveris time per selected page: {summary['audiveris_stats']['mean']} ms.
- Mean MIDI conversion time: {summary['midi_stats']['mean']} ms.
- Mean music features extraction time: {summary['features_stats']['mean']} ms.
- Mean total time per page: {summary['total_stats']['mean']} ms.

## Rough extrapolation

- remaining_music_mixed_without_mxl: {summary['remaining_count']}.
- estimated_total_time_hours: {summary['estimated_total_hours']}.
- This is a rough estimate from a small sample and does not change final VKR metrics.

## Defense wording

Music features are extracted from MXL/MusicXML, so pages without MXL require OMR first. A separate benchmark shows that preprocessing and feature extraction take milliseconds, while the main computational cost comes from Audiveris. A full run over all music/mixed pages is a separate batch task and was not mixed with final VKR metrics.

## Outputs

- Sample pages: `{sample_csv.relative_to(PROJECT_ROOT)}`
- Raw timing: `{raw_csv.relative_to(PROJECT_ROOT)}`
- Report: `{report_path.relative_to(PROJECT_ROOT)}`
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-size", type=int, default=10)
    parser.add_argument("--validated", type=Path, default=DEFAULT_VALIDATED)
    parser.add_argument("--sample-csv", type=Path, default=DEFAULT_SAMPLE_CSV)
    parser.add_argument("--raw-csv", type=Path, default=DEFAULT_RAW_CSV)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--notes", type=Path, default=DEFAULT_NOTES)
    parser.add_argument("--omr-dir", type=Path, default=DEFAULT_OMR_DIR)
    parser.add_argument("--midi-dir", type=Path, default=DEFAULT_MIDI_DIR)
    parser.add_argument("--audiveris-bin", default="audiveris")
    parser.add_argument("--remaining-music-mixed-without-mxl", type=int, default=1873)
    parser.add_argument("--roots", type=Path, nargs="*", default=DEFAULT_ROOTS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.sample_size <= 0 or args.sample_size > 10:
        raise SystemExit("--sample-size must be between 1 and 10")
    validated_rows = read_validated_pages(args.validated)
    artifact_index = build_artifact_index(list(args.roots))
    sample_rows = select_sample(validated_rows, artifact_index, args.sample_size)
    write_csv(args.sample_csv, sample_rows, SAMPLE_COLUMNS)
    raw_rows = benchmark_sample(sample_rows, args.omr_dir, args.midi_dir, args.audiveris_bin)
    write_csv(args.raw_csv, raw_rows, RAW_COLUMNS)
    summary = summarize(raw_rows, args.remaining_music_mixed_without_mxl)
    write_report(args.report, summary, raw_rows, args.sample_csv, args.raw_csv)
    write_notes(args.notes, summary, args.report, args.raw_csv, args.sample_csv)
    print(f"Selected pages: {summary['selected_pages']}")
    print(f"MXL/MIDI/features: {summary['mxl_created']}/{summary['midi_created']}/{summary['features_extracted']}")
    print(f"Mean Audiveris ms: {summary['audiveris_stats']['mean']}")
    print(f"Mean features ms: {summary['features_stats']['mean']}")
    print(f"Estimated hours for remaining {summary['remaining_count']}: {summary['estimated_total_hours']}")
    print(f"Sample CSV: {args.sample_csv}")
    print(f"Raw CSV: {args.raw_csv}")
    print(f"Report: {args.report}")
    print(f"Notes: {args.notes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
