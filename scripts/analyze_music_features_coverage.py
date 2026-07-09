"""Analyze music feature coverage for existing MXL/MusicXML artifacts.

This script does not run Audiveris. It only parses already existing
MXL/MusicXML files and reports which metadata/features can be extracted.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from notevision.music_features import extract_music_features, identify_musicxml_page  # noqa: E402

DEFAULT_OUTPUT = PROJECT_ROOT / "outputs" / "reports" / "music_features_coverage_report.md"
DEFAULT_CSV = PROJECT_ROOT / "outputs" / "reports" / "music_features_coverage.csv"
DEFAULT_NOTES = PROJECT_ROOT / "docs" / "thesis" / "local_vkr" / "music_features_coverage_notes.md"
DEFAULT_ROOTS = [
    PROJECT_ROOT / "outputs",
    PROJECT_ROOT / "data" / "processed",
]
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "019ea8da-d9e4-7af0-ae29-9df7a0100da5",
}

CSV_COLUMNS = [
    "doc_id",
    "page_index",
    "mxl_path",
    "midi_exists",
    "extraction_status",
    "has_key_signature",
    "key_signature",
    "key_name_ru",
    "key_name_latin",
    "mode",
    "has_time_signature",
    "time_signature",
    "has_clefs",
    "clefs",
    "has_parts",
    "parts_count",
    "has_instruments",
    "instruments",
    "measures_count",
    "confidence",
    "source",
    "duration_ms",
    "error",
]


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _is_unknown(value: object) -> bool:
    text = str(value or "").strip().lower()
    return text in {"", "unknown", "none", "nan"}


def _positive_int(value: object) -> bool:
    try:
        return int(float(str(value or "0"))) > 0
    except ValueError:
        return False


def is_project_musicxml(path: Path) -> bool:
    """Return True for MXL and likely MusicXML files inside project outputs."""
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return False
    suffix = path.suffix.lower()
    if suffix == ".mxl":
        return True
    if suffix not in {".musicxml", ".xml"}:
        return False
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:4096].lower()
    except OSError:
        return False
    return any(
        marker in head
        for marker in (
            "<score-partwise",
            "<score-timewise",
            "<opus",
            "musicxml",
        )
    )


def find_existing_musicxml_files(roots: Iterable[Path]) -> list[Path]:
    """Find all existing project MXL/MusicXML files deterministically."""
    files: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        iterator = root.rglob("*")
        for path in iterator:
            if not path.is_file() or path.suffix.lower() not in {".mxl", ".musicxml", ".xml"}:
                continue
            if not is_project_musicxml(path):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(path)
    return sorted(files, key=lambda value: str(value).lower())


def find_related_midi(doc_id: str, page_index: str) -> bool:
    """Find an existing MIDI for a doc/page using known project naming."""
    if doc_id == "unknown" or page_index == "unknown":
        return False
    try:
        page_number = int(float(page_index))
    except ValueError:
        return False
    page_name = f"page_{page_number:03d}"
    for root in PROJECT_ROOT.glob("outputs/midi*"):
        if not root.is_dir():
            continue
        doc_dir = root / doc_id
        if not doc_dir.exists():
            continue
        patterns = [
            f"{page_name}.mid",
            f"{page_name}.midi",
            f"{page_name}*.mid",
            f"{page_name}*.midi",
        ]
        for pattern in patterns:
            if any(path.is_file() for path in doc_dir.rglob(pattern)):
                return True
    return False


def analyze_one(path: Path) -> dict[str, object]:
    """Extract coverage fields and timing for one MXL/MusicXML file."""
    doc_id, page_index, id_error = identify_musicxml_page(path)
    start = time.perf_counter()
    features = extract_music_features(path, doc_id=doc_id, page_index=page_index)
    duration_ms = (time.perf_counter() - start) * 1000.0
    status = str(features.get("extraction_status", "failed"))
    error = "; ".join(
        value
        for value in (id_error, str(features.get("error", "") or ""))
        if value
    )
    has_key = not _is_unknown(features.get("key_signature")) or not _is_unknown(
        features.get("key_name_latin")
    )
    has_time = not _is_unknown(features.get("time_signature"))
    has_clefs = not _is_unknown(features.get("clefs"))
    has_parts = _positive_int(features.get("parts_count")) or not _is_unknown(
        features.get("parts")
    )
    has_instruments = not _is_unknown(features.get("instruments"))
    return {
        "doc_id": doc_id,
        "page_index": page_index,
        "mxl_path": _relative(path),
        "midi_exists": int(find_related_midi(doc_id, page_index)),
        "extraction_status": "failed" if status in {"parse_error", "missing_file"} else status,
        "has_key_signature": int(has_key),
        "key_signature": features.get("key_signature", "unknown"),
        "key_name_ru": features.get("key_name_ru", "unknown"),
        "key_name_latin": features.get("key_name_latin", "unknown"),
        "mode": features.get("mode", "unknown"),
        "has_time_signature": int(has_time),
        "time_signature": features.get("time_signature", "unknown"),
        "has_clefs": int(has_clefs),
        "clefs": features.get("clefs", "unknown"),
        "has_parts": int(has_parts),
        "parts_count": features.get("parts_count", 0),
        "has_instruments": int(has_instruments),
        "instruments": features.get("instruments", "unknown"),
        "measures_count": features.get("measures_count", 0),
        "confidence": features.get("confidence", 0.0),
        "source": features.get("source", "unknown"),
        "duration_ms": round(duration_ms, 3),
        "error": error,
    }


def pct(value: int, total: int) -> float:
    return round(value * 100.0 / total, 2) if total else 0.0


def parsed_ok(row: dict[str, object]) -> bool:
    return str(row["extraction_status"]) != "failed"


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    total = len(rows)
    success = sum(parsed_ok(row) for row in rows)
    failed = total - success
    durations = [float(row["duration_ms"]) for row in rows]
    return {
        "total": total,
        "parsed_success": success,
        "parsed_failed": failed,
        "success_rate": pct(success, total),
        "key_count": sum(int(row["has_key_signature"]) for row in rows),
        "time_count": sum(int(row["has_time_signature"]) for row in rows),
        "clefs_count": sum(int(row["has_clefs"]) for row in rows),
        "parts_count": sum(int(row["has_parts"]) for row in rows),
        "instruments_count": sum(int(row["has_instruments"]) for row in rows),
        "measures_count": sum(_positive_int(row["measures_count"]) for row in rows),
        "midi_count": sum(int(row["midi_exists"]) for row in rows),
        "mean_ms": round(statistics.fmean(durations), 3) if durations else 0.0,
        "median_ms": round(statistics.median(durations), 3) if durations else 0.0,
        "min_ms": round(min(durations), 3) if durations else 0.0,
        "max_ms": round(max(durations), 3) if durations else 0.0,
        "total_seconds": round(sum(durations) / 1000.0, 3),
    }


def top_counter(rows: list[dict[str, object]], column: str, *, split: bool = False, limit: int = 10) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for row in rows:
        value = str(row.get(column, "") or "").strip()
        if _is_unknown(value):
            continue
        values = [item.strip() for item in value.split(";")] if split else [value]
        for item in values:
            if item and not _is_unknown(item):
                counter[item] += 1
    return counter.most_common(limit)


def count_distribution(rows: list[dict[str, object]], column: str) -> list[tuple[str, int]]:
    counter = Counter(str(row.get(column, "") or "") for row in rows)
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def coverage_row(label: str, count: int, total: int) -> str:
    return f"| {label} | {count} | {pct(count, total)}% |"


def write_report(path: Path, rows: list[dict[str, object]], summary: dict[str, object], csv_path: Path) -> None:
    total = int(summary["total"])
    lines = [
        "# Music features coverage report",
        "",
        f"- Run timestamp: {datetime.now().isoformat(timespec='seconds')}",
        "- Scope: existing project MXL/MusicXML files only.",
        "- Audiveris invoked: no.",
        f"- CSV: `{_relative(csv_path)}`",
        "",
        "## Overall",
        "",
        f"- total_mxl_musicxml_files: {summary['total']}",
        f"- parsed_success: {summary['parsed_success']}",
        f"- parsed_failed: {summary['parsed_failed']}",
        f"- success_rate: {summary['success_rate']}%",
        "",
        "## Feature Coverage",
        "",
        "| feature | files | coverage |",
        "|---|---:|---:|",
        coverage_row("key_signature / key_name", int(summary["key_count"]), total),
        coverage_row("time_signature", int(summary["time_count"]), total),
        coverage_row("clefs", int(summary["clefs_count"]), total),
        coverage_row("parts", int(summary["parts_count"]), total),
        coverage_row("instruments", int(summary["instruments_count"]), total),
        coverage_row("measures_count", int(summary["measures_count"]), total),
        coverage_row("linked MIDI", int(summary["midi_count"]), total),
        "",
        "## Timing",
        "",
        "| count | mean_ms | median_ms | min_ms | max_ms | total_seconds |",
        "|---:|---:|---:|---:|---:|---:|",
        f"| {summary['total']} | {summary['mean_ms']} | {summary['median_ms']} | {summary['min_ms']} | {summary['max_ms']} | {summary['total_seconds']} |",
        "",
    ]
    for title, values in (
        ("Top key signatures", top_counter(rows, "key_signature")),
        ("Top time signatures", top_counter(rows, "time_signature", split=True)),
        ("Top instruments", top_counter(rows, "instruments", split=True)),
        ("Parts count distribution", count_distribution(rows, "parts_count")),
        ("Confidence distribution", count_distribution(rows, "confidence")),
        ("Source distribution", count_distribution(rows, "source")),
    ):
        lines.extend([f"## {title}", "", "| value | count |", "|---|---:|"])
        for value, count in values:
            lines.append(f"| {value} | {count} |")
        lines.append("")
    lines.extend(
        [
            "## Limitations",
            "",
            "- This is coverage of feature extraction from existing MXL/MusicXML, not a repeated OMR run.",
            "- This is not musical correctness and not expert validation.",
            "- Missing metadata does not necessarily mean a wrong OMR result; some files may not contain explicit key/time/instrument metadata.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_notes(path: Path, summary: dict[str, object], report_path: Path, csv_path: Path) -> None:
    total = int(summary["total"])
    text = f"""# music_features_coverage_notes

DOCX VKR and defense PPTX/PDF were not changed. Git was not touched. Audiveris was not invoked.

## Human Summary

- Existing MXL/MusicXML files checked: {summary['total']}.
- Successfully parsed: {summary['parsed_success']}.
- Failed: {summary['parsed_failed']}.
- Key signature / key name extracted in {summary['key_count']} of {total} files ({pct(int(summary['key_count']), total)}%).
- Time signature extracted in {summary['time_count']} of {total} files ({pct(int(summary['time_count']), total)}%).
- Clefs extracted in {summary['clefs_count']} of {total} files ({pct(int(summary['clefs_count']), total)}%).
- Parts extracted in {summary['parts_count']} of {total} files ({pct(int(summary['parts_count']), total)}%).
- Instruments extracted in {summary['instruments_count']} of {total} files ({pct(int(summary['instruments_count']), total)}%).
- Measures count extracted in {summary['measures_count']} of {total} files ({pct(int(summary['measures_count']), total)}%).
- Linked MIDI found for {summary['midi_count']} of {total} files ({pct(int(summary['midi_count']), total)}%).
- Extraction timing: mean {summary['mean_ms']} ms, median {summary['median_ms']} ms, min {summary['min_ms']} ms, max {summary['max_ms']} ms per file; total {summary['total_seconds']} s.

## Defense Wording

Separately, feature coverage was calculated for already obtained MXL/MusicXML files. This is not a repeated OMR run and not expert validation of musical correctness. It shows which structured fields could be extracted from existing OMR artifacts: key signature, time signature, clefs, parts, instruments, and measure count.

Use the wording: on existing MXL/MusicXML, feature X was found in N of M files. Do not say that the system correctly determined tonality, instruments, or musical correctness without expert validation.

## Outputs

- Report: `{_relative(report_path)}`
- CSV: `{_relative(csv_path)}`
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--notes", type=Path, default=DEFAULT_NOTES)
    parser.add_argument(
        "--root",
        type=Path,
        action="append",
        help="Root to scan. Defaults to outputs/ and data/processed/.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    roots = args.root or DEFAULT_ROOTS
    files = find_existing_musicxml_files(roots)
    rows = [analyze_one(path) for path in files]
    summary = summarize(rows)
    write_csv(args.csv, rows)
    write_report(args.output, rows, summary, args.csv)
    write_notes(args.notes, summary, args.output, args.csv)
    print(f"MXL/MusicXML files found: {summary['total']}")
    print(f"Parsed successfully: {summary['parsed_success']}")
    print(f"Failed: {summary['parsed_failed']}")
    print(
        "Coverage key/time/clefs/parts/instruments: "
        f"{summary['key_count']}/{summary['time_count']}/"
        f"{summary['clefs_count']}/{summary['parts_count']}/"
        f"{summary['instruments_count']}"
    )
    print(
        "Timing mean/median/min/max ms: "
        f"{summary['mean_ms']}/{summary['median_ms']}/"
        f"{summary['min_ms']}/{summary['max_ms']}"
    )
    print(f"Report: {args.output}")
    print(f"CSV: {args.csv}")
    print(f"Notes: {args.notes}")


if __name__ == "__main__":
    main()
