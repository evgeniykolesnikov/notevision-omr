"""Build a reproducible, priority-aware sample for thesis OMR evaluation."""

from __future__ import annotations

import argparse
import csv
import random
from collections import Counter
from pathlib import Path
from typing import Iterable

KEY_COLUMNS = ["doc_id", "page_index"]
REQUIRED_COLUMNS = [
    *KEY_COLUMNS,
    "page_type",
    "has_music",
    "has_music_score",
    "validation_source",
]
OMR_EVAL_GROUP_COLUMN = "omr_eval_group"

GROUP_MANUAL = "manual_validated"
GROUP_TEMPLATE = "template_prediction"
GROUP_ORDER = [GROUP_MANUAL, GROUP_TEMPLATE]

MANUAL_SOURCES = {"manual_previous", "manual_thesis"}
PROBLEMATIC_DOC_IDS = {
    "rsl01010549152",
    "rsl01013687437",
    "rsl01013957967",
}
ELIGIBLE_PAGE_TYPES = {"music", "mixed"}


def _page_key(row: dict[str, str]) -> tuple[str, int]:
    doc_id = str(row.get("doc_id", "")).strip()
    try:
        page_index = int(str(row.get("page_index", "")).strip())
    except ValueError as error:
        raise ValueError(
            f"Invalid page_index for document {doc_id or '<empty>'}: "
            f"{row.get('page_index', '')}"
        ) from error
    if not doc_id or page_index < 1:
        raise ValueError(
            "Labels contain an empty doc_id or non-positive page_index"
        )
    return doc_id, page_index


def _binary(row: dict[str, str], column: str) -> int:
    key = _page_key(row)
    try:
        value = int(float(str(row.get(column, "")).strip()))
    except ValueError as error:
        raise ValueError(
            f"Invalid {column} for {key[0]}/page_{key[1]}: "
            f"{row.get(column, '')}"
        ) from error
    if value not in {0, 1}:
        raise ValueError(
            f"{column} must be 0 or 1 for {key[0]}/page_{key[1]}"
        )
    return value


def _score(row: dict[str, str]) -> float:
    key = _page_key(row)
    try:
        return float(str(row.get("has_music_score", "")).strip())
    except ValueError as error:
        raise ValueError(
            f"Invalid has_music_score for {key[0]}/page_{key[1]}: "
            f"{row.get('has_music_score', '')}"
        ) from error


def _evaluation_group(row: dict[str, str]) -> str:
    source = str(row.get("validation_source", "")).strip()
    if source in MANUAL_SOURCES:
        return GROUP_MANUAL
    if source == GROUP_TEMPLATE:
        return GROUP_TEMPLATE
    key = _page_key(row)
    raise ValueError(
        f"Unknown validation_source for {key[0]}/page_{key[1]}: {source!r}"
    )


def _priority_count(row: dict[str, str]) -> int:
    """Count independent reasons for selecting a page before random fill."""
    doc_id, _ = _page_key(row)
    page_type = str(row.get("page_type", "")).strip().lower()
    source = str(row.get("validation_source", "")).strip()
    return sum(
        (
            source in MANUAL_SOURCES,
            page_type == "mixed",
            doc_id in PROBLEMATIC_DOC_IDS,
            _score(row) < 0.95,
        )
    )


def _unique_eligible_rows(
    labels_rows: Iterable[dict[str, str]],
) -> dict[tuple[str, int], dict[str, str]]:
    unique: dict[tuple[str, int], dict[str, str]] = {}
    for source_row in labels_rows:
        row = dict(source_row)
        page_type = str(row.get("page_type", "")).strip().lower()
        if _binary(row, "has_music") != 1:
            continue
        if page_type not in ELIGIBLE_PAGE_TYPES:
            continue
        unique.setdefault(_page_key(row), row)
    return unique


def build_omr_eval_sample(
    labels_rows: Iterable[dict[str, str]],
    *,
    limit: int = 150,
    random_seed: int = 42,
) -> list[dict[str, str]]:
    """Select eligible pages while retaining priority categories first."""
    if limit < 0:
        raise ValueError(f"limit must be zero or positive, got: {limit}")

    rows_by_key = _unique_eligible_rows(labels_rows)
    if limit == 0 or not rows_by_key:
        return []

    candidates = []
    for key, source_row in rows_by_key.items():
        row = dict(source_row)
        row[OMR_EVAL_GROUP_COLUMN] = _evaluation_group(row)
        candidates.append((key, row, _priority_count(row)))

    generator = random.Random(random_seed)
    generator.shuffle(candidates)
    candidates.sort(key=lambda item: item[2], reverse=True)
    selected = candidates[: min(limit, len(candidates))]

    return [
        row
        for _, row, _ in sorted(
            selected,
            key=lambda item: (item[0][0], item[0][1]),
        )
    ]


def _read_labels(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        raise FileNotFoundError(f"Labels CSV does not exist: {path}")
    try:
        with path.open(encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            columns = list(reader.fieldnames or [])
            missing = [
                column for column in REQUIRED_COLUMNS if column not in columns
            ]
            if missing:
                raise ValueError(
                    "Labels CSV is missing required columns: "
                    + ", ".join(missing)
                )
            return columns, list(reader)
    except UnicodeError as error:
        raise ValueError(f"Could not decode labels CSV as UTF-8: {path}") from error
    except csv.Error as error:
        raise ValueError(f"Could not parse labels CSV {path}: {error}") from error


def write_omr_eval_sample(
    labels_path: Path,
    output_path: Path,
    *,
    limit: int = 150,
    random_seed: int = 42,
) -> dict[str, object]:
    """Read labels, save the OMR sample, and return summary values."""
    input_columns, labels_rows = _read_labels(labels_path)
    eligible_rows = _unique_eligible_rows(labels_rows)
    sample_rows = build_omr_eval_sample(
        labels_rows,
        limit=limit,
        random_seed=random_seed,
    )
    output_columns = [
        column for column in input_columns if column != OMR_EVAL_GROUP_COLUMN
    ] + [OMR_EVAL_GROUP_COLUMN]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=output_columns,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(sample_rows)

    group_counts = Counter(
        row[OMR_EVAL_GROUP_COLUMN] for row in sample_rows
    )
    return {
        "eligible_pages": len(eligible_rows),
        "sample_pages": len(sample_rows),
        "group_counts": group_counts,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=150)
    parser.add_argument("--random-seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        summary = write_omr_eval_sample(
            args.labels,
            args.out,
            limit=args.limit,
            random_seed=args.random_seed,
        )
    except (FileNotFoundError, ValueError, OSError) as error:
        raise SystemExit(f"Error: {error}") from error

    print(f"Eligible pages: {summary['eligible_pages']}")
    print(f"Sample pages: {summary['sample_pages']}")
    print("Groups:")
    group_counts = summary["group_counts"]
    for group in GROUP_ORDER:
        print(f"  {group}: {group_counts.get(group, 0)}")
    print(f"Output: {args.out}")


if __name__ == "__main__":
    main()
