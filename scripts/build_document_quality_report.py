"""Build per-document page quality statistics from validated labels."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

REPORT_COLUMNS = [
    "doc_id",
    "total_pages",
    "music_pages",
    "text_pages",
    "title_pages",
    "blank_pages",
    "bad_scan_pages",
    "unknown_pages",
    "photo_scan_like",
    "handwritten_music_like",
]
REQUIRED_COLUMNS = {"doc_id", "page_type", "has_music", "quality_comment"}

PHOTO_SCAN_MARKERS = (
    "photo scan",
    "photo_scan",
    "photograph",
    "photographed",
    "camera",
    "kodak",
    "color control patch",
    "фотосним",
    "фотограф",
)
HANDWRITTEN_MARKERS = (
    "handwritten",
    "hand-written",
    "manuscript",
    "рукопис",
)


def _contains_marker(comment: str, markers: tuple[str, ...]) -> bool:
    lowered = comment.casefold()
    return any(marker in lowered for marker in markers)


def build_document_quality_rows(
    labels_rows: list[dict[str, str]],
) -> list[dict[str, object]]:
    """Aggregate page-type and comment-derived quality counts by document."""
    documents: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in labels_rows:
        doc_id = row.get("doc_id", "").strip()
        if not doc_id:
            raise ValueError("Labels CSV contains an empty doc_id")
        documents[doc_id].append(row)

    report: list[dict[str, object]] = []
    for doc_id in sorted(documents):
        rows = documents[doc_id]
        page_types = [row.get("page_type", "").strip().lower() for row in rows]
        report.append(
            {
                "doc_id": doc_id,
                "total_pages": len(rows),
                "music_pages": sum(
                    row.get("has_music", "").strip() == "1" for row in rows
                ),
                "text_pages": page_types.count("text"),
                "title_pages": page_types.count("title"),
                "blank_pages": page_types.count("blank"),
                "bad_scan_pages": page_types.count("bad_scan"),
                "unknown_pages": page_types.count("unknown"),
                "photo_scan_like": sum(
                    _contains_marker(
                        row.get("quality_comment", ""),
                        PHOTO_SCAN_MARKERS,
                    )
                    for row in rows
                ),
                "handwritten_music_like": sum(
                    _contains_marker(
                        row.get("quality_comment", ""),
                        HANDWRITTEN_MARKERS,
                    )
                    for row in rows
                ),
            }
        )
    return report


def _read_labels(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Labels CSV does not exist: {path}")
    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        columns = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise ValueError(
                "Labels CSV is missing required columns: " + ", ".join(missing)
            )
        return list(reader)


def write_document_quality_report(
    labels_path: Path,
    output_path: Path,
) -> list[dict[str, object]]:
    """Build and save document quality statistics."""
    rows = build_document_quality_rows(_read_labels(labels_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        rows = write_document_quality_report(args.labels, args.out)
    except (FileNotFoundError, ValueError, OSError, csv.Error) as error:
        raise SystemExit(f"Error: {error}") from error
    print(f"Documents: {len(rows)}")
    print(f"Pages: {sum(int(row['total_pages']) for row in rows)}")
    print(f"Report: {args.out}")


if __name__ == "__main__":
    main()
