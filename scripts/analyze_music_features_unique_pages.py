"""Map existing MXL/MusicXML artifacts to unique validated pages.

The script does not run Audiveris. It selects one existing MXL/MusicXML result
per validated corpus page, extracts metadata features, and keeps key signature
metadata separate from inferred musical key analysis.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from notevision.music_features import extract_music_features, identify_musicxml_page  # noqa: E402

DEFAULT_VALIDATED = PROJECT_ROOT / "data" / "labels" / "pages_validated_thesis.csv"
DEFAULT_REPORT = PROJECT_ROOT / "outputs" / "reports" / "music_features_unique_pages_report.md"
DEFAULT_CSV = PROJECT_ROOT / "outputs" / "reports" / "music_features_by_unique_page.csv"
DEFAULT_NOTES = PROJECT_ROOT / "docs" / "thesis" / "local_vkr" / "music_features_unique_pages_notes.md"
DEFAULT_ORIGIN_NOTES = PROJECT_ROOT / "docs" / "thesis" / "local_vkr" / "music_features_coverage_origin_notes.md"
DEFAULT_ROOTS = [PROJECT_ROOT / "outputs", PROJECT_ROOT / "data" / "processed"]

EXCLUDED_PARTS = {".git", ".venv", "__pycache__", "node_modules", "019ea8da-d9e4-7af0-ae29-9df7a0100da5"}

CSV_COLUMNS = [
    "doc_id",
    "page_index",
    "page_type",
    "has_music",
    "mxl_exists",
    "selected_mxl_path",
    "selected_variant",
    "duplicate_mxl_count",
    "midi_exists",
    "extraction_status",
    "explicit_key_signature_found",
    "key_fifths",
    "zero_key_signature",
    "key_candidates",
    "key_name_metadata",
    "key_name_inferred",
    "key_inference_reason",
    "time_signature_found",
    "time_signature",
    "clefs_found",
    "clefs",
    "parts_found",
    "parts_count",
    "instruments_found",
    "instruments",
    "measures_count_found",
    "measures_count",
    "confidence",
    "source",
    "parse_extract_duration_ms",
    "error",
]

MAJOR = {
    -7: "Cb major",
    -6: "Gb major",
    -5: "Db major",
    -4: "Ab major",
    -3: "Eb major",
    -2: "Bb major",
    -1: "F major",
    0: "C major",
    1: "G major",
    2: "D major",
    3: "A major",
    4: "E major",
    5: "B major",
    6: "F# major",
    7: "C# major",
}
MINOR = {
    -7: "Ab minor",
    -6: "Eb minor",
    -5: "Bb minor",
    -4: "F minor",
    -3: "C minor",
    -2: "G minor",
    -1: "D minor",
    0: "A minor",
    1: "E minor",
    2: "B minor",
    3: "F# minor",
    4: "C# minor",
    5: "G# minor",
    6: "D# minor",
    7: "A# minor",
}


@dataclass(frozen=True)
class MxlArtifact:
    path: Path
    doc_id: str
    page_index: str
    variant: str
    priority: int
    path_prefix: str


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def is_unknown(value: object) -> bool:
    return str(value or "").strip().lower() in {"", "unknown", "none", "nan"}


def truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "1.0", "true", "yes"}


def positive_int(value: object) -> bool:
    try:
        return int(float(str(value or "0"))) > 0
    except ValueError:
        return False


def pct(value: int, total: int) -> float:
    return round(value * 100.0 / total, 2) if total else 0.0


def is_project_musicxml(path: Path) -> bool:
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
    return any(marker in head for marker in ("<score-partwise", "<score-timewise", "<opus", "musicxml"))


def classify_variant(path: Path) -> tuple[str, int]:
    text = str(path).replace("\\", "/").lower()
    name = path.name.lower()
    if "pipeline_test_combined" in text or "final" in text:
        return "final", 1
    if "400dpi_fallback" in text or "400dpi" in name:
        return "400dpi_fallback", 2
    if "preprocessed_fallback" in text or "preprocessing_fallback" in text or "crop_" in text:
        return "preprocessing_fallback", 3
    if "omr_eval_300" in text or "omr_300dpi" in text or "primary_omr" in text or "/omr/" in text:
        return "primary", 4
    return "unknown", 5


def path_prefix(path: Path) -> str:
    parts = path.resolve().relative_to(PROJECT_ROOT).parts
    if len(parts) >= 2 and parts[0] == "outputs":
        return "/".join(parts[:2])
    if len(parts) >= 2 and parts[0] == "data":
        return "/".join(parts[:2])
    return parts[0] if parts else "unknown"


def find_artifacts(roots: list[Path]) -> list[MxlArtifact]:
    artifacts: list[MxlArtifact] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".mxl", ".musicxml", ".xml"}:
                continue
            if not is_project_musicxml(path):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            doc_id, page_index, _ = identify_musicxml_page(path)
            variant, priority = classify_variant(path)
            artifacts.append(MxlArtifact(path, doc_id, page_index, variant, priority, path_prefix(path)))
    return sorted(artifacts, key=lambda item: (item.doc_id, item.page_index, item.priority, rel(item.path).lower()))


def read_validated_pages(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def page_key(doc_id: str, page_index: object) -> tuple[str, str]:
    try:
        page = str(int(float(str(page_index))))
    except ValueError:
        page = str(page_index or "").strip()
    return doc_id, page


def key_candidates(key_fifths: object) -> str:
    try:
        fifths = int(float(str(key_fifths)))
    except ValueError:
        return ""
    major = MAJOR.get(fifths)
    minor = MINOR.get(fifths)
    if not major or not minor:
        return ""
    return f"{major} / {minor}"


def find_related_midi(doc_id: str, page_index: str) -> bool:
    if doc_id == "unknown" or page_index == "unknown":
        return False
    try:
        page_name = f"page_{int(float(page_index)):03d}"
    except ValueError:
        return False
    for root in PROJECT_ROOT.glob("outputs/midi*"):
        if not root.is_dir():
            continue
        doc_dir = root / doc_id
        if not doc_dir.exists():
            continue
        for pattern in (f"{page_name}.mid", f"{page_name}.midi", f"{page_name}*.mid", f"{page_name}*.midi"):
            if any(path.is_file() for path in doc_dir.rglob(pattern)):
                return True
    return False


def extract_selected(artifact: MxlArtifact | None) -> tuple[dict[str, object], float]:
    if artifact is None:
        return {}, 0.0
    start = time.perf_counter()
    row = extract_music_features(artifact.path, doc_id=artifact.doc_id, page_index=artifact.page_index)
    return row, (time.perf_counter() - start) * 1000.0


def build_unique_rows(validated_rows: list[dict[str, str]], artifacts: list[MxlArtifact]) -> list[dict[str, object]]:
    by_page: dict[tuple[str, str], list[MxlArtifact]] = defaultdict(list)
    for artifact in artifacts:
        if artifact.doc_id != "unknown" and artifact.page_index != "unknown":
            by_page[(artifact.doc_id, artifact.page_index)].append(artifact)

    rows: list[dict[str, object]] = []
    for page in validated_rows:
        doc_id, page_index = page_key(str(page.get("doc_id", "")).strip(), page.get("page_index", ""))
        candidates = sorted(by_page.get((doc_id, page_index), []), key=lambda item: (item.priority, rel(item.path).lower()))
        selected = candidates[0] if candidates else None
        features, duration_ms = extract_selected(selected)
        raw_status = str(features.get("extraction_status", "")) if features else ""
        extraction_status = "no_mxl" if selected is None else ("failed" if raw_status in {"parse_error", "missing_file"} else raw_status)
        explicit_key = selected is not None and not is_unknown(features.get("key_fifths"))
        key_fifths = features.get("key_fifths", "") if explicit_key else ""
        zero_key = explicit_key and str(key_fifths) in {"0", "0.0"}
        mode_status = str(features.get("mode_status", ""))
        metadata_key = str(features.get("detected_tonality_latin", "") or "")
        if mode_status != "detected" or is_unknown(metadata_key):
            metadata_key = ""
        time_signature = str(features.get("time_signature", "") or "")
        clefs = str(features.get("clefs", "") or "")
        instruments = str(features.get("instruments", "") or "")
        parts_count = features.get("parts_count", 0)
        measures_count = features.get("measures_count", 0)
        rows.append(
            {
                "doc_id": doc_id,
                "page_index": page_index,
                "page_type": str(page.get("page_type", "")).strip(),
                "has_music": str(page.get("has_music", "")).strip(),
                "mxl_exists": int(selected is not None),
                "selected_mxl_path": rel(selected.path) if selected else "",
                "selected_variant": selected.variant if selected else "",
                "duplicate_mxl_count": max(len(candidates) - 1, 0),
                "midi_exists": int(find_related_midi(doc_id, page_index)),
                "extraction_status": extraction_status,
                "explicit_key_signature_found": int(explicit_key),
                "key_fifths": key_fifths,
                "zero_key_signature": int(zero_key),
                "key_candidates": key_candidates(key_fifths),
                "key_name_metadata": metadata_key,
                "key_name_inferred": "",
                "key_inference_reason": "not_run",
                "time_signature_found": int(not is_unknown(time_signature)),
                "time_signature": "" if is_unknown(time_signature) else time_signature,
                "clefs_found": int(not is_unknown(clefs)),
                "clefs": "" if is_unknown(clefs) else clefs,
                "parts_found": int(positive_int(parts_count)),
                "parts_count": parts_count if selected else "",
                "instruments_found": int(not is_unknown(instruments)),
                "instruments": "" if is_unknown(instruments) else instruments,
                "measures_count_found": int(positive_int(measures_count)),
                "measures_count": measures_count if selected else "",
                "confidence": features.get("confidence", "") if selected else "",
                "source": features.get("source", "") if selected else "",
                "parse_extract_duration_ms": round(duration_ms, 3),
                "error": str(features.get("error", "") or "") if selected else "",
            }
        )
    return rows


def summarize(unique_rows: list[dict[str, object]], artifacts: list[MxlArtifact]) -> dict[str, object]:
    total_pages = len(unique_rows)
    pages_with_mxl = sum(int(row["mxl_exists"]) for row in unique_rows)
    pages_with_midi = sum(int(row["midi_exists"]) for row in unique_rows)
    rows_with_mxl = [row for row in unique_rows if int(row["mxl_exists"])]
    music_mixed = [row for row in unique_rows if str(row["page_type"]).lower() in {"music", "mixed"}]
    durations = [float(row["parse_extract_duration_ms"]) for row in rows_with_mxl]
    return {
        "total_files": len(artifacts),
        "unique_docs": len({item.doc_id for item in artifacts if item.doc_id != "unknown"}),
        "unique_doc_pages_in_artifacts": len({(item.doc_id, item.page_index) for item in artifacts if item.doc_id != "unknown" and item.page_index != "unknown"}),
        "duplicates_count": len(artifacts) - len({(item.doc_id, item.page_index) for item in artifacts if item.doc_id != "unknown" and item.page_index != "unknown"}),
        "total_validated_pages": total_pages,
        "pages_with_mxl": pages_with_mxl,
        "pages_with_midi": pages_with_midi,
        "parsed_success": sum(str(row["extraction_status"]) not in {"failed", "no_mxl"} for row in rows_with_mxl),
        "parsed_failed": sum(str(row["extraction_status"]) == "failed" for row in rows_with_mxl),
        "explicit_key": sum(int(row["explicit_key_signature_found"]) for row in rows_with_mxl),
        "zero_key": sum(int(row["zero_key_signature"]) for row in rows_with_mxl),
        "key_candidates": sum(1 for row in rows_with_mxl if str(row["key_candidates"]).strip()),
        "inferred_key": sum(1 for row in rows_with_mxl if str(row["key_name_inferred"]).strip()),
        "time_signature": sum(int(row["time_signature_found"]) for row in rows_with_mxl),
        "clefs": sum(int(row["clefs_found"]) for row in rows_with_mxl),
        "parts": sum(int(row["parts_found"]) for row in rows_with_mxl),
        "instruments": sum(int(row["instruments_found"]) for row in rows_with_mxl),
        "measures": sum(int(row["measures_count_found"]) for row in rows_with_mxl),
        "total_music_mixed_pages": len(music_mixed),
        "music_mixed_with_mxl": sum(int(row["mxl_exists"]) for row in music_mixed),
        "music_mixed_with_features": sum(
            int(row["mxl_exists"]) and str(row["extraction_status"]) not in {"failed", "no_mxl"}
            for row in music_mixed
        ),
        "mean_ms": round(statistics.fmean(durations), 3) if durations else 0.0,
        "median_ms": round(statistics.median(durations), 3) if durations else 0.0,
        "min_ms": round(min(durations), 3) if durations else 0.0,
        "max_ms": round(max(durations), 3) if durations else 0.0,
        "total_seconds": round(sum(durations) / 1000, 3),
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_origin_notes(path: Path, artifacts: list[MxlArtifact], summary: dict[str, object]) -> None:
    prefix_counts = Counter(item.path_prefix for item in artifacts)
    variant_counts = Counter(item.variant for item in artifacts)
    lines = [
        "# music_features_coverage_origin_notes",
        "",
        "The previous count of 571 refers to MXL/MusicXML files, not unique corpus pages.",
        "",
        "## Overall",
        "",
        f"- total_mxl_musicxml_files: {summary['total_files']}",
        f"- unique_doc_id: {summary['unique_docs']}",
        f"- unique_doc_id_page_index: {summary['unique_doc_pages_in_artifacts']}",
        f"- duplicates_count: {summary['duplicates_count']}",
        "",
        "## By Path Prefix",
        "",
        "| path_prefix | count |",
        "|---|---:|",
    ]
    for prefix, count in prefix_counts.most_common():
        lines.append(f"| {prefix} | {count} |")
    lines.extend(["", "## By Variant", "", "| variant | count |", "|---|---:|"])
    for variant, count in variant_counts.most_common():
        lines.append(f"| {variant} | {count} |")
    lines.extend(
        [
            "",
            "Duplicates appear because the project stores primary, fallback, preprocessed, 400 DPI, movement-split and other OMR artifacts. Unique-page coverage therefore uses one selected MXL/MusicXML per validated page.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_report(path: Path, rows: list[dict[str, object]], summary: dict[str, object]) -> None:
    pages_with_mxl = int(summary["pages_with_mxl"])
    lines = [
        "# Music features coverage by unique validated page",
        "",
        f"- Run timestamp: {datetime.now().isoformat(timespec='seconds')}",
        "- Scope: existing validated pages and already existing MXL/MusicXML only.",
        "- Audiveris invoked: no.",
        "",
        "## Origin of MXL/MusicXML files",
        "",
        f"- total_mxl_musicxml_files: {summary['total_files']}",
        f"- unique_doc_id: {summary['unique_docs']}",
        f"- unique_doc_id_page_index: {summary['unique_doc_pages_in_artifacts']}",
        f"- duplicates_count: {summary['duplicates_count']}",
        "",
        "## All Validated Pages",
        "",
        "| metric | value | percent |",
        "|---|---:|---:|",
        f"| total_validated_pages | {summary['total_validated_pages']} | 100% |",
        f"| pages_with_mxl | {summary['pages_with_mxl']} | {pct(int(summary['pages_with_mxl']), int(summary['total_validated_pages']))}% |",
        f"| pages_with_midi | {summary['pages_with_midi']} | {pct(int(summary['pages_with_midi']), int(summary['total_validated_pages']))}% |",
        "",
        "## Pages With Selected MXL/MusicXML",
        "",
        "| feature | pages | coverage among pages with MXL |",
        "|---|---:|---:|",
        f"| parsed_success | {summary['parsed_success']} | {pct(int(summary['parsed_success']), pages_with_mxl)}% |",
        f"| parsed_failed | {summary['parsed_failed']} | {pct(int(summary['parsed_failed']), pages_with_mxl)}% |",
        f"| explicit_key_signature_found | {summary['explicit_key']} | {pct(int(summary['explicit_key']), pages_with_mxl)}% |",
        f"| zero_key_signature | {summary['zero_key']} | {pct(int(summary['zero_key']), pages_with_mxl)}% |",
        f"| key_candidates_available | {summary['key_candidates']} | {pct(int(summary['key_candidates']), pages_with_mxl)}% |",
        f"| inferred_key_available | {summary['inferred_key']} | {pct(int(summary['inferred_key']), pages_with_mxl)}% |",
        f"| time_signature_found | {summary['time_signature']} | {pct(int(summary['time_signature']), pages_with_mxl)}% |",
        f"| clefs_found | {summary['clefs']} | {pct(int(summary['clefs']), pages_with_mxl)}% |",
        f"| parts_found | {summary['parts']} | {pct(int(summary['parts']), pages_with_mxl)}% |",
        f"| instruments_found | {summary['instruments']} | {pct(int(summary['instruments']), pages_with_mxl)}% |",
        f"| measures_count_found | {summary['measures']} | {pct(int(summary['measures']), pages_with_mxl)}% |",
        "",
        "## Music/Mixed Pages",
        "",
        "| metric | value | percent |",
        "|---|---:|---:|",
        f"| total_music_mixed_pages | {summary['total_music_mixed_pages']} | 100% |",
        f"| music_mixed_with_mxl | {summary['music_mixed_with_mxl']} | {pct(int(summary['music_mixed_with_mxl']), int(summary['total_music_mixed_pages']))}% |",
        f"| music_mixed_with_features | {summary['music_mixed_with_features']} | {pct(int(summary['music_mixed_with_features']), int(summary['total_music_mixed_pages']))}% |",
        "",
        "## Timing",
        "",
        "| pages_with_mxl | mean_ms | median_ms | min_ms | max_ms | total_seconds |",
        "|---:|---:|---:|---:|---:|---:|",
        f"| {summary['pages_with_mxl']} | {summary['mean_ms']} | {summary['median_ms']} | {summary['min_ms']} | {summary['max_ms']} | {summary['total_seconds']} |",
        "",
        "## Key Interpretation",
        "",
        "- explicit_key_signature_found means that MusicXML contains key/fifths metadata.",
        "- zero_key_signature means 0 accidentals; it is represented as possible C major / A minor, not as a confirmed key.",
        "- key_name_inferred is empty because music21.analyze('key') was not run in this analysis.",
        "- Absence of explicit key metadata is not the same as absence of tonality.",
        "",
        "## Limitations",
        "",
        "- This is not a repeated OMR run.",
        "- This is not musical correctness and not expert validation.",
        "- One MXL/MusicXML is selected per validated page by priority: final, successful fallback, primary, then first existing/unknown.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_notes(path: Path, summary: dict[str, object], origin_path: Path, report_path: Path, csv_path: Path) -> None:
    text = f"""# music_features_unique_pages_notes

DOCX VKR and defense PPTX/PDF were not changed. Git was not touched. Audiveris was not invoked.

## What changed compared with file-level coverage

- The previous `571` value is the number of MXL/MusicXML files found in project outputs.
- These files map to {summary['unique_doc_pages_in_artifacts']} unique doc_id/page_index pairs.
- Duplicates count: {summary['duplicates_count']}.
- The unique-page report selects one MXL/MusicXML per validated page.

## Unique-page coverage

- Total validated pages: {summary['total_validated_pages']}.
- Pages with selected MXL/MusicXML: {summary['pages_with_mxl']} ({pct(int(summary['pages_with_mxl']), int(summary['total_validated_pages']))}%).
- Pages with linked MIDI: {summary['pages_with_midi']} ({pct(int(summary['pages_with_midi']), int(summary['total_validated_pages']))}%).
- Parsed success among pages with MXL: {summary['parsed_success']} of {summary['pages_with_mxl']}.
- Parsed failed among pages with MXL: {summary['parsed_failed']} of {summary['pages_with_mxl']}.
- Explicit key signature found: {summary['explicit_key']} of {summary['pages_with_mxl']}.
- Zero key signature cases: {summary['zero_key']}.
- Key candidates available: {summary['key_candidates']} of {summary['pages_with_mxl']}.
- Time signature found: {summary['time_signature']} of {summary['pages_with_mxl']}.
- Clefs found: {summary['clefs']} of {summary['pages_with_mxl']}.
- Parts found: {summary['parts']} of {summary['pages_with_mxl']}.
- Instruments found: {summary['instruments']} of {summary['pages_with_mxl']}.
- Measures count found: {summary['measures']} of {summary['pages_with_mxl']}.

## Music/mixed pages

- Total music/mixed pages: {summary['total_music_mixed_pages']}.
- Music/mixed with MXL: {summary['music_mixed_with_mxl']}.
- Music/mixed with parsed features: {summary['music_mixed_with_features']}.

## Key handling

Key signature is treated as metadata. If `key_fifths=0`, the report writes possible `C major / A minor`, not confirmed C major. No inferred key analysis was run, so `key_name_inferred` is empty and `key_inference_reason=not_run`. Absence of explicit key metadata is not absence of tonality.

## Timing

- Mean: {summary['mean_ms']} ms.
- Median: {summary['median_ms']} ms.
- Min/max: {summary['min_ms']} ms / {summary['max_ms']} ms.
- Total: {summary['total_seconds']} s.

## Defense wording

Musical features are extracted not directly from the image, but from already obtained MXL/MusicXML. Therefore I separately calculate feature coverage for pages where OMR produced a structured artifact. For key, it is important to separate explicit key signature metadata from inferred musical key: 0 accidentals can correspond to C major or A minor and does not mean absence of tonality.

This is not musical correctness and not an expert validation of the score.

## Outputs

- Origin notes: `{rel(origin_path)}`
- Report: `{rel(report_path)}`
- CSV: `{rel(csv_path)}`
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validated-pages", type=Path, default=DEFAULT_VALIDATED)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--notes", type=Path, default=DEFAULT_NOTES)
    parser.add_argument("--origin-notes", type=Path, default=DEFAULT_ORIGIN_NOTES)
    parser.add_argument("--root", type=Path, action="append")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifacts = find_artifacts(args.root or DEFAULT_ROOTS)
    validated_rows = read_validated_pages(args.validated_pages)
    unique_rows = build_unique_rows(validated_rows, artifacts)
    summary = summarize(unique_rows, artifacts)
    write_csv(args.csv, unique_rows)
    write_origin_notes(args.origin_notes, artifacts, summary)
    write_report(args.report, unique_rows, summary)
    write_notes(args.notes, summary, args.origin_notes, args.report, args.csv)
    print(f"Total MXL/MusicXML files: {summary['total_files']}")
    print(f"Unique doc/page pairs in artifacts: {summary['unique_doc_pages_in_artifacts']}")
    print(f"Total validated pages: {summary['total_validated_pages']}")
    print(f"Pages with selected MXL: {summary['pages_with_mxl']}")
    print(f"Parsed success/failed: {summary['parsed_success']}/{summary['parsed_failed']}")
    print(
        "Feature coverage key/time/clefs/parts/instruments: "
        f"{summary['explicit_key']}/{summary['time_signature']}/"
        f"{summary['clefs']}/{summary['parts']}/{summary['instruments']}"
    )
    print(
        "Timing mean/median/min/max ms: "
        f"{summary['mean_ms']}/{summary['median_ms']}/{summary['min_ms']}/{summary['max_ms']}"
    )
    print(f"Origin notes: {args.origin_notes}")
    print(f"Report: {args.report}")
    print(f"CSV: {args.csv}")
    print(f"Notes: {args.notes}")


if __name__ == "__main__":
    main()
