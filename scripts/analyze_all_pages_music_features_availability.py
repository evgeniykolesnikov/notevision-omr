"""Summarize music feature availability for all validated corpus pages.

This script does not run Audiveris or any OMR step. It maps already existing
PNG, MXL/MusicXML, MIDI and parsed music-feature metadata to validated pages.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import datetime
from pathlib import Path

from analyze_music_features_unique_pages import (
    DEFAULT_ROOTS,
    DEFAULT_VALIDATED,
    PROJECT_ROOT,
    build_unique_rows,
    find_artifacts,
    page_key,
    pct,
    read_validated_pages,
)

DEFAULT_OMR300 = PROJECT_ROOT / "data" / "labels" / "omr_eval_sample_300_thesis.csv"
DEFAULT_REPORT = PROJECT_ROOT / "outputs" / "reports" / "all_pages_music_features_availability_report.md"
DEFAULT_CSV = PROJECT_ROOT / "outputs" / "reports" / "all_pages_music_features_availability.csv"
DEFAULT_NOTES = PROJECT_ROOT / "docs" / "thesis" / "local_vkr" / "all_pages_music_features_availability_notes.md"

CSV_COLUMNS = [
    "doc_id",
    "page_index",
    "page_type",
    "has_music",
    "in_omr300",
    "png_exists",
    "image_path",
    "mxl_exists",
    "midi_exists",
    "parsed_music_features",
    "features_absence_reason",
    "selected_mxl_path",
    "selected_variant",
    "extraction_status",
]


def truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "1.0", "true", "yes"}


def rel_or_empty(path_value: object) -> str:
    return str(path_value or "").strip()


def local_path_exists(path_value: object) -> bool:
    raw = rel_or_empty(path_value)
    if not raw:
        return False
    normalized = raw.replace("\\", "/")
    path = Path(normalized)
    if path.is_absolute():
        return path.exists()
    return (PROJECT_ROOT / path).exists()


def read_omr300_keys(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        return {
            page_key(str(row.get("doc_id", "")).strip(), row.get("page_index", ""))
            for row in csv.DictReader(csv_file)
        }


def has_parsed_features(row: dict[str, object]) -> bool:
    return bool(int(row["mxl_exists"])) and str(row["extraction_status"]) not in {"failed", "no_mxl"}


def absence_reason(row: dict[str, object]) -> str:
    if has_parsed_features(row):
        return ""
    page_type = str(row.get("page_type", "")).strip().lower()
    has_music = truthy(row.get("has_music"))
    if not int(row["mxl_exists"]):
        if page_type not in {"music", "mixed"} and not has_music:
            return "non_music_page"
        return "no_mxl_musicxml"
    if str(row["extraction_status"]) == "failed":
        return "mxl_parse_failed"
    return "unknown"


def build_rows(validated_rows: list[dict[str, str]], unique_rows: list[dict[str, object]], omr300_keys: set[tuple[str, str]]) -> list[dict[str, object]]:
    by_key = {(str(row["doc_id"]), str(row["page_index"])): row for row in unique_rows}
    rows: list[dict[str, object]] = []
    for page in validated_rows:
        doc_id, page_index = page_key(str(page.get("doc_id", "")).strip(), page.get("page_index", ""))
        unique = by_key[(doc_id, page_index)]
        parsed = has_parsed_features(unique)
        row = {
            "doc_id": doc_id,
            "page_index": page_index,
            "page_type": str(page.get("page_type", "")).strip(),
            "has_music": str(page.get("has_music", "")).strip(),
            "in_omr300": int((doc_id, page_index) in omr300_keys),
            "png_exists": int(local_path_exists(page.get("image_path", ""))),
            "image_path": rel_or_empty(page.get("image_path", "")),
            "mxl_exists": int(unique["mxl_exists"]),
            "midi_exists": int(unique["midi_exists"]),
            "parsed_music_features": int(parsed),
            "features_absence_reason": absence_reason(unique),
            "selected_mxl_path": unique["selected_mxl_path"],
            "selected_variant": unique["selected_variant"],
            "extraction_status": unique["extraction_status"],
        }
        rows.append(row)
    return rows


def summarize_subset(rows: list[dict[str, object]]) -> dict[str, object]:
    total = len(rows)
    reasons = Counter(str(row["features_absence_reason"]) for row in rows if str(row["features_absence_reason"]).strip())
    return {
        "total_validated_pages": total,
        "page_type_distribution": Counter(str(row["page_type"]) for row in rows),
        "pages_with_png": sum(int(row["png_exists"]) for row in rows),
        "pages_with_mxl": sum(int(row["mxl_exists"]) for row in rows),
        "pages_with_midi": sum(int(row["midi_exists"]) for row in rows),
        "pages_with_parsed_music_features": sum(int(row["parsed_music_features"]) for row in rows),
        "pages_without_mxl": sum(1 for row in rows if not int(row["mxl_exists"])),
        "features_absence_reasons": reasons,
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def metric_lines(summary: dict[str, object]) -> list[str]:
    total = int(summary["total_validated_pages"])
    lines = [
        "| metric | value | percent |",
        "|---|---:|---:|",
        f"| total_validated_pages | {total} | 100% |",
        f"| pages_with_png | {summary['pages_with_png']} | {pct(int(summary['pages_with_png']), total)}% |",
        f"| pages_with_mxl | {summary['pages_with_mxl']} | {pct(int(summary['pages_with_mxl']), total)}% |",
        f"| pages_with_midi | {summary['pages_with_midi']} | {pct(int(summary['pages_with_midi']), total)}% |",
        f"| pages_with_parsed_music_features | {summary['pages_with_parsed_music_features']} | {pct(int(summary['pages_with_parsed_music_features']), total)}% |",
        f"| pages_without_mxl | {summary['pages_without_mxl']} | {pct(int(summary['pages_without_mxl']), total)}% |",
    ]
    return lines


def distribution_lines(summary: dict[str, object]) -> list[str]:
    distribution: Counter[str] = summary["page_type_distribution"]
    total = int(summary["total_validated_pages"])
    lines = ["| page_type | pages | percent |", "|---|---:|---:|"]
    for page_type, count in sorted(distribution.items()):
        lines.append(f"| {page_type or 'unknown'} | {count} | {pct(count, total)}% |")
    return lines


def reason_lines(summary: dict[str, object]) -> list[str]:
    reasons: Counter[str] = summary["features_absence_reasons"]
    total = int(summary["total_validated_pages"])
    lines = ["| reason | pages | percent of subset |", "|---|---:|---:|"]
    for reason in ("no_mxl_musicxml", "mxl_parse_failed", "non_music_page", "unknown"):
        count = reasons.get(reason, 0)
        lines.append(f"| {reason} | {count} | {pct(count, total)}% |")
    return lines


def write_report(path: Path, rows: list[dict[str, object]], omr300_found: bool) -> dict[str, dict[str, object]]:
    all_summary = summarize_subset(rows)
    music_mixed_rows = [row for row in rows if str(row["page_type"]).lower() in {"music", "mixed"}]
    omr300_rows = [row for row in rows if int(row["in_omr300"])]
    summaries = {
        "all_pages": all_summary,
        "music_mixed_pages": summarize_subset(music_mixed_rows),
        "omr300_pages": summarize_subset(omr300_rows),
    }
    lines = [
        "# All-pages music features availability",
        "",
        f"- Run timestamp: {datetime.now().isoformat(timespec='seconds')}",
        "- Scope: all validated corpus pages and already existing PNG, MXL/MusicXML, MIDI and reports.",
        "- Audiveris invoked: no.",
        "- DOCX/PPTX/PDF files changed: no.",
        "",
        "## All Pages",
        "",
        *metric_lines(summaries["all_pages"]),
        "",
        "### Page Type Distribution",
        "",
        *distribution_lines(summaries["all_pages"]),
        "",
        "### Reasons Without Parsed Music Features",
        "",
        *reason_lines(summaries["all_pages"]),
        "",
        "## Music/Mixed Pages",
        "",
        *metric_lines(summaries["music_mixed_pages"]),
        "",
        "### Page Type Distribution",
        "",
        *distribution_lines(summaries["music_mixed_pages"]),
        "",
        "### Reasons Without Parsed Music Features",
        "",
        *reason_lines(summaries["music_mixed_pages"]),
        "",
        "## OMR-300 Pages",
        "",
        f"- OMR-300 sample file found: {'yes' if omr300_found else 'no'}.",
        "",
        *metric_lines(summaries["omr300_pages"]),
        "",
        "### Page Type Distribution",
        "",
        *distribution_lines(summaries["omr300_pages"]),
        "",
        "### Reasons Without Parsed Music Features",
        "",
        *reason_lines(summaries["omr300_pages"]),
        "",
        "## Interpretation",
        "",
        "- Music features are extracted only from existing MXL/MusicXML artifacts.",
        "- Absence of parsed features on a page does not mean absence of music on the scanned page.",
        "- For pages without MXL/MusicXML, an OMR step is needed before music-feature extraction can be evaluated.",
        "- OMR-300 availability here reflects existing artifacts found in the workspace and is not a replacement for final OMR-300 technical-success metrics in the VKR.",
        "- This summary is not musical correctness and not expert validation.",
        "",
        "## Defense wording",
        "",
        "> We accounted for all validated corpus pages and matched them with existing OMR artifacts. Music features are extracted only where MXL/MusicXML already exists. Therefore feature coverage is calculated separately from OMR technical success.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return summaries


def write_notes(path: Path, summaries: dict[str, dict[str, object]], report_path: Path, csv_path: Path) -> None:
    all_summary = summaries["all_pages"]
    music_summary = summaries["music_mixed_pages"]
    omr_summary = summaries["omr300_pages"]
    text = f"""# all_pages_music_features_availability_notes

DOCX VKR, defense PPTX/PDF and final VKR metrics were not changed. Git was not touched. Audiveris was not invoked.

## Scope

- All validated pages of the corpus were accounted for: {all_summary['total_validated_pages']}.
- Music features are extracted only from already existing MXL/MusicXML.
- Absence of features on a page does not mean absence of music.
- For pages without MXL/MusicXML, an OMR step is needed before music-feature extraction can be evaluated.
- OMR-300 availability in this note reflects existing artifacts found in the workspace and does not replace final OMR-300 technical-success metrics in the VKR.
- This is not musical correctness and not expert validation.

## All pages

- pages_with_png: {all_summary['pages_with_png']}.
- pages_with_mxl: {all_summary['pages_with_mxl']}.
- pages_with_midi: {all_summary['pages_with_midi']}.
- pages_with_parsed_music_features: {all_summary['pages_with_parsed_music_features']}.
- pages_without_mxl: {all_summary['pages_without_mxl']}.

## Music/mixed pages

- total: {music_summary['total_validated_pages']}.
- pages_with_mxl: {music_summary['pages_with_mxl']}.
- pages_with_midi: {music_summary['pages_with_midi']}.
- pages_with_parsed_music_features: {music_summary['pages_with_parsed_music_features']}.
- pages_without_mxl: {music_summary['pages_without_mxl']}.

## OMR-300 pages

- total: {omr_summary['total_validated_pages']}.
- pages_with_mxl: {omr_summary['pages_with_mxl']}.
- pages_with_midi: {omr_summary['pages_with_midi']}.
- pages_with_parsed_music_features: {omr_summary['pages_with_parsed_music_features']}.
- pages_without_mxl: {omr_summary['pages_without_mxl']}.

## Defense wording

We accounted for all validated corpus pages and matched them with existing OMR artifacts. Music features are extracted only where MXL/MusicXML already exists. Therefore feature coverage is calculated separately from OMR technical success.

## Outputs

- Report: `{report_path.relative_to(PROJECT_ROOT)}`
- CSV: `{csv_path.relative_to(PROJECT_ROOT)}`
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validated", type=Path, default=DEFAULT_VALIDATED)
    parser.add_argument("--omr300", type=Path, default=DEFAULT_OMR300)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--notes", type=Path, default=DEFAULT_NOTES)
    parser.add_argument("--roots", type=Path, nargs="*", default=DEFAULT_ROOTS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    validated_rows = read_validated_pages(args.validated)
    artifacts = find_artifacts(list(args.roots))
    unique_rows = build_unique_rows(validated_rows, artifacts)
    omr300_keys = read_omr300_keys(args.omr300)
    rows = build_rows(validated_rows, unique_rows, omr300_keys)
    write_csv(args.csv, rows)
    summaries = write_report(args.report, rows, args.omr300.exists())
    write_notes(args.notes, summaries, args.report, args.csv)

    all_summary = summaries["all_pages"]
    music_summary = summaries["music_mixed_pages"]
    omr_summary = summaries["omr300_pages"]
    print(f"Total validated pages: {all_summary['total_validated_pages']}")
    print(f"Page types: {dict(sorted(all_summary['page_type_distribution'].items()))}")
    print(f"All pages with PNG/MXL/MIDI/features: {all_summary['pages_with_png']}/{all_summary['pages_with_mxl']}/{all_summary['pages_with_midi']}/{all_summary['pages_with_parsed_music_features']}")
    print(f"All pages without MXL: {all_summary['pages_without_mxl']}")
    print(f"Music/mixed pages with MXL/features: {music_summary['pages_with_mxl']}/{music_summary['pages_with_parsed_music_features']} of {music_summary['total_validated_pages']}")
    print(f"OMR-300 pages with MXL/features: {omr_summary['pages_with_mxl']}/{omr_summary['pages_with_parsed_music_features']} of {omr_summary['total_validated_pages']}")
    print(f"Report: {args.report}")
    print(f"CSV: {args.csv}")
    print(f"Notes: {args.notes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
