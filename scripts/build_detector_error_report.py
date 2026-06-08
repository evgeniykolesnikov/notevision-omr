"""Build per-document detector error statistics from validated labels."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

REPORT_COLUMNS = [
    "doc_id",
    "detector_music_pages",
    "validated_music_pages",
    "false_music",
    "false_non_music",
    "unknown_rate",
    "bad_scan_rate",
]
REQUIRED_COLUMNS = {"doc_id", "page_type", "has_music", "has_music_pred"}


def _binary(row: dict[str, str], column: str) -> int:
    try:
        value = int(float(row.get(column, "")))
    except ValueError as error:
        raise ValueError(
            f"Invalid {column} for {row.get('doc_id', '<missing>')}/"
            f"page_{row.get('page_index', '<missing>')}: {row.get(column, '')}"
        ) from error
    if value not in {0, 1}:
        raise ValueError(f"{column} must contain only 0 or 1")
    return value


def build_detector_error_rows(
    labels_rows: list[dict[str, str]],
) -> list[dict[str, object]]:
    """Aggregate detector errors and page-quality rates by document."""
    documents: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in labels_rows:
        doc_id = row.get("doc_id", "").strip()
        if not doc_id:
            raise ValueError("Labels CSV contains an empty doc_id")
        documents[doc_id].append(row)

    report: list[dict[str, object]] = []
    for doc_id, rows in documents.items():
        actual = [_binary(row, "has_music") for row in rows]
        predicted = [_binary(row, "has_music_pred") for row in rows]
        page_types = [row.get("page_type", "").strip().lower() for row in rows]
        total = len(rows)
        report.append(
            {
                "doc_id": doc_id,
                "detector_music_pages": sum(predicted),
                "validated_music_pages": sum(actual),
                "false_music": sum(
                    truth == 0 and prediction == 1
                    for truth, prediction in zip(actual, predicted)
                ),
                "false_non_music": sum(
                    truth == 1 and prediction == 0
                    for truth, prediction in zip(actual, predicted)
                ),
                "unknown_rate": page_types.count("unknown") / total if total else 0,
                "bad_scan_rate": (
                    page_types.count("bad_scan") / total if total else 0
                ),
            }
        )

    return sorted(
        report,
        key=lambda row: (
            -(int(row["false_music"]) + int(row["false_non_music"])),
            str(row["doc_id"]),
        ),
    )


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


def write_detector_error_report(
    labels_path: Path,
    output_path: Path,
) -> list[dict[str, object]]:
    """Build and save detector errors ordered by error count."""
    rows = build_detector_error_rows(_read_labels(labels_path))
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
        rows = write_detector_error_report(args.labels, args.out)
    except (FileNotFoundError, ValueError, OSError, csv.Error) as error:
        raise SystemExit(f"Error: {error}") from error

    print(f"Documents: {len(rows)}")
    print("Top detector errors:")
    for row in rows[:10]:
        errors = int(row["false_music"]) + int(row["false_non_music"])
        print(
            f"  {row['doc_id']}: {errors} "
            f"(false_music={row['false_music']}, "
            f"false_non_music={row['false_non_music']})"
        )
    print(f"Report: {args.out}")


if __name__ == "__main__":
    main()
