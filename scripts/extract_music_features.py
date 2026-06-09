"""Extract music-theoretical features from MXL/MusicXML files."""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from notevision.music_features import (  # noqa: E402
    FEATURE_COLUMNS,
    extract_music_features,
    find_musicxml_files,
    identify_musicxml_page,
)


def extract_directory_features(
    mxl_dir: Path,
    *,
    recursive: bool = False,
) -> list[dict[str, object]]:
    """Extract every supported score under a directory."""
    return [
        extract_music_features(path)
        for path in find_musicxml_files(mxl_dir, recursive=recursive)
    ]


def extract_multiple_directories(
    directories: list[Path],
    *,
    recursive: bool = False,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[Path] = set()
    for directory in directories:
        for path in find_musicxml_files(directory, recursive=recursive):
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                rows.append(extract_music_features(path))
    return rows


def _first_value(row: dict[str, str], names: tuple[str, ...]) -> str:
    return next(
        (
            str(row.get(name, "")).strip()
            for name in names
            if str(row.get(name, "")).strip()
        ),
        "",
    )


def _resolve_report_path(value: str, report_path: Path) -> Path:
    normalized = Path(value.replace("\\", "/"))
    if normalized.is_absolute():
        return normalized
    project_candidate = PROJECT_ROOT / normalized
    if project_candidate.exists():
        return project_candidate
    return report_path.parent / normalized


def _find_page_artifact(
    roots: list[Path],
    doc_id: str,
    page_index: int,
    extensions: set[str],
) -> Path | None:
    page_name = f"page_{page_index:03d}"
    candidates = []
    for root in roots:
        page_dir = root / doc_id / page_name
        if page_dir.is_dir():
            candidates.extend(
                path
                for path in page_dir.rglob("*")
                if path.is_file() and path.suffix.lower() in extensions
            )
        candidates.extend(
            path
            for path in (root / doc_id).glob(f"{page_name}*")
            if path.is_file() and path.suffix.lower() in extensions
        )
    return sorted(candidates, key=lambda path: str(path).lower())[0] if candidates else None


def extract_report_features(
    report_path: Path,
    *,
    search_roots: list[Path] | None = None,
) -> list[dict[str, object]]:
    """Extract files named in an OMR report or resolve them by doc/page."""
    if not report_path.is_file():
        raise FileNotFoundError(f"OMR report does not exist: {report_path}")
    roots = search_roots or [
        PROJECT_ROOT / "outputs" / "omr",
        PROJECT_ROOT / "outputs" / "omr_300dpi",
        PROJECT_ROOT / "outputs" / "omr_400dpi_fallback",
        PROJECT_ROOT / "outputs" / "omr_preprocessed_fallback",
    ]
    with report_path.open(encoding="utf-8-sig", newline="") as csv_file:
        rows = list(csv.DictReader(csv_file))

    results = []
    seen_paths: set[Path] = set()
    for row in rows:
        doc_id = str(row.get("doc_id", "")).strip() or "unknown"
        page_text = str(row.get("page_index", "")).strip()
        if not page_text:
            # Aggregate pipeline reports identify documents rather than pages.
            for root in roots:
                document_dir = root / doc_id
                if not document_dir.is_dir():
                    continue
                for source_path in find_musicxml_files(
                    document_dir, recursive=True
                ):
                    resolved = source_path.resolve()
                    if resolved in seen_paths:
                        continue
                    seen_paths.add(resolved)
                    inferred_doc, inferred_page, _ = identify_musicxml_page(
                        source_path
                    )
                    midi = (
                        _find_page_artifact(
                            [PROJECT_ROOT / "outputs" / "midi"],
                            doc_id,
                            int(inferred_page),
                            {".mid", ".midi"},
                        )
                        if inferred_page != "unknown"
                        else None
                    )
                    results.append(
                        extract_music_features(
                            source_path,
                            doc_id=doc_id if doc_id != "unknown" else inferred_doc,
                            page_index=inferred_page,
                            midi_path=str(midi) if midi else "",
                        )
                    )
            continue
        try:
            page_index: int | str = int(float(page_text))
        except ValueError:
            page_index = page_text or "unknown"
        source_value = _first_value(
            row,
            (
                "mxl_path",
                "musicxml_path",
                "source_mxl",
                "fallback_400_mxl_path",
                "preprocessing_mxl_path",
                "source_path",
            ),
        )
        source_path = (
            _resolve_report_path(source_value, report_path)
            if source_value
            else _find_page_artifact(
                roots,
                doc_id,
                int(page_index) if isinstance(page_index, int) else -1,
                {".mxl", ".musicxml", ".xml"},
            )
        )
        if source_path is None:
            source_path = roots[0] / doc_id / f"page_{page_index}" / "missing.mxl"
        resolved_source = source_path.resolve()
        if resolved_source in seen_paths:
            continue
        seen_paths.add(resolved_source)
        midi_value = _first_value(
            row,
            (
                "midi_path",
                "fallback_400_midi_path",
                "preprocessing_midi_path",
            ),
        )
        if not midi_value and isinstance(page_index, int):
            midi = _find_page_artifact(
                [PROJECT_ROOT / "outputs" / "midi"],
                doc_id,
                page_index,
                {".mid", ".midi"},
            )
            midi_value = str(midi) if midi else ""
        results.append(
            extract_music_features(
                source_path,
                doc_id=doc_id,
                page_index=page_index,
                midi_path=midi_value,
            )
        )
    return results


def write_feature_csv(rows: list[dict[str, object]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FEATURE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(rows: list[dict[str, object]], summary_path: Path) -> None:
    statuses = Counter(str(row["extraction_status"]) for row in rows)
    sources = Counter(str(row["source"]) for row in rows)
    documents = {
        str(row["doc_id"]) for row in rows if row["doc_id"] != "unknown"
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        "\n".join(
            [
                "# Music features extraction summary",
                "",
                f"- Files processed: {len(rows)}",
                f"- Documents: {len(documents)}",
                f"- Success: {statuses['success']}",
                f"- No key: {statuses['no_key']}",
                f"- No time signature: {statuses['no_time_signature']}",
                f"- Parse errors: {statuses['parse_error']}",
                f"- Missing files: {statuses['missing_file']}",
                f"- Key source musicxml: {sources['musicxml']}",
                f"- Key source not_found: {sources['not_found']}",
                "",
                "`source=musicxml` means that the key signature was read "
                "directly from MusicXML. `source=not_found` means that the "
                "extractor did not infer or invent an absent value.",
                "",
                "Если MusicXML содержит только key signature без mode, "
                "система показывает пару параллельных тональностей и не "
                "делает эвристического вывода о мажоре/миноре.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--omr-report", type=Path)
    source_group.add_argument(
        "--input-dir",
        "--mxl-dir",
        dest="input_dirs",
        type=Path,
        action="append",
        help="May be repeated for primary and fallback OMR directories.",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--recursive", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        rows = (
            extract_report_features(args.omr_report)
            if args.omr_report is not None
            else extract_multiple_directories(
                args.input_dirs,
                recursive=args.recursive,
            )
        )
        write_feature_csv(rows, args.out)
        summary_path = args.summary or args.out.with_name(
            f"{args.out.stem}_summary.md"
        )
        write_summary(rows, summary_path)
    except (FileNotFoundError, OSError, ValueError) as error:
        raise SystemExit(f"Error: {error}") from error
    statuses = Counter(str(row["extraction_status"]) for row in rows)
    print(f"MusicXML files processed: {len(rows)}")
    print(f"Success: {statuses['success']}")
    print(f"No key: {statuses['no_key']}")
    print(f"No time signature: {statuses['no_time_signature']}")
    print(f"Parse errors: {statuses['parse_error']}")
    print(f"Missing files: {statuses['missing_file']}")
    print(f"CSV: {args.out}")
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()
