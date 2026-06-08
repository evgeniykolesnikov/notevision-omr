"""Build a deterministic page-review sample for the thesis corpus."""

from __future__ import annotations

import argparse
import csv
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

KEY_COLUMNS = ["doc_id", "page_index"]
REQUIRED_COLUMNS = [
    *KEY_COLUMNS,
    "page_type",
    "has_music_pred",
    "has_music_score",
    "validation_source",
]
REVIEW_REASON_COLUMN = "review_reason"

REASON_TEMPLATE = "template_prediction"
REASON_UNKNOWN = "unknown"
REASON_UNCERTAIN = "uncertain_score"
REASON_FIRST = "first_2_pages"
REASON_LAST = "last_2_pages"
REASON_LOW_MUSIC = "low_confidence_music"
REASON_HIGH_NON_MUSIC = "high_score_non_music"
REASON_RANDOM_MUSIC = "random_confident_music"

REASON_ORDER = [
    REASON_TEMPLATE,
    REASON_UNKNOWN,
    REASON_UNCERTAIN,
    REASON_FIRST,
    REASON_LAST,
    REASON_LOW_MUSIC,
    REASON_HIGH_NON_MUSIC,
    REASON_RANDOM_MUSIC,
]


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


def _score(row: dict[str, str]) -> float:
    key = _page_key(row)
    try:
        return float(row["has_music_score"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            f"Invalid has_music_score for {key[0]}/page_{key[1]}: "
            f"{row.get('has_music_score', '')}"
        ) from error


def _prediction(row: dict[str, str]) -> int:
    key = _page_key(row)
    try:
        prediction = int(float(row["has_music_pred"]))
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            f"Invalid has_music_pred for {key[0]}/page_{key[1]}: "
            f"{row.get('has_music_pred', '')}"
        ) from error
    if prediction not in {0, 1}:
        raise ValueError(
            f"has_music_pred must be 0 or 1 for "
            f"{key[0]}/page_{key[1]}"
        )
    return prediction


def _unique_rows(
    rows: Iterable[dict[str, str]],
) -> dict[tuple[str, int], dict[str, str]]:
    unique: dict[tuple[str, int], dict[str, str]] = {}
    for row in rows:
        key = _page_key(row)
        unique.setdefault(key, dict(row))
    return unique


def build_thesis_review_sample(
    labels_rows: Iterable[dict[str, str]],
    *,
    random_music: int = 100,
    random_seed: int = 42,
) -> list[dict[str, str]]:
    """Select review pages and attach all applicable reasons."""
    if random_music < 0:
        raise ValueError(
            f"random_music must be zero or positive, got: {random_music}"
        )

    rows_by_key = _unique_rows(labels_rows)
    reasons: defaultdict[tuple[str, int], set[str]] = defaultdict(set)
    pages_by_doc: defaultdict[str, list[tuple[str, int]]] = defaultdict(list)

    for key, row in rows_by_key.items():
        pages_by_doc[key[0]].append(key)
        score = _score(row)
        prediction = _prediction(row)

        if row.get("validation_source", "").strip() == REASON_TEMPLATE:
            reasons[key].add(REASON_TEMPLATE)
        if row.get("page_type", "").strip().lower() == "unknown":
            reasons[key].add(REASON_UNKNOWN)
        if 0.1 <= score <= 0.9:
            reasons[key].add(REASON_UNCERTAIN)
        if prediction == 1 and score < 0.95:
            reasons[key].add(REASON_LOW_MUSIC)
        if prediction == 0 and score > 0.05:
            reasons[key].add(REASON_HIGH_NON_MUSIC)

    for document_keys in pages_by_doc.values():
        ordered = sorted(document_keys, key=lambda key: key[1])
        for key in ordered[:2]:
            reasons[key].add(REASON_FIRST)
        for key in ordered[-2:]:
            reasons[key].add(REASON_LAST)

    confident_music = sorted(
        (
            key
            for key, row in rows_by_key.items()
            if _prediction(row) == 1 and _score(row) >= 0.95
        ),
        key=lambda key: (key[0], key[1]),
    )
    sample_size = min(random_music, len(confident_music))
    random_generator = random.Random(random_seed)
    for key in random_generator.sample(confident_music, sample_size):
        reasons[key].add(REASON_RANDOM_MUSIC)

    reason_position = {
        reason: position for position, reason in enumerate(REASON_ORDER)
    }
    selected: list[dict[str, str]] = []
    for key in sorted(reasons, key=lambda item: (item[0], item[1])):
        row = dict(rows_by_key[key])
        row[REVIEW_REASON_COLUMN] = ";".join(
            sorted(
                reasons[key],
                key=lambda reason: reason_position[reason],
            )
        )
        selected.append(row)
    return selected


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


def write_thesis_review_sample(
    labels_path: Path,
    output_path: Path,
    *,
    random_music: int = 100,
    random_seed: int = 42,
) -> dict[str, object]:
    """Read labels, write the review sample, and return summary data."""
    input_columns, labels_rows = _read_labels(labels_path)
    sample_rows = build_thesis_review_sample(
        labels_rows,
        random_music=random_music,
        random_seed=random_seed,
    )
    output_columns = [
        column for column in input_columns if column != REVIEW_REASON_COLUMN
    ] + [REVIEW_REASON_COLUMN]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=output_columns,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(sample_rows)

    reason_counts: Counter[str] = Counter()
    for row in sample_rows:
        reason_counts.update(row[REVIEW_REASON_COLUMN].split(";"))

    return {
        "total_labels": len(labels_rows),
        "review_sample": len(sample_rows),
        "reason_counts": reason_counts,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--random-music", type=int, default=100)
    parser.add_argument("--random-seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        summary = write_thesis_review_sample(
            args.labels,
            args.out,
            random_music=args.random_music,
            random_seed=args.random_seed,
        )
    except (FileNotFoundError, ValueError, OSError) as error:
        raise SystemExit(f"Error: {error}") from error

    print(f"Total labels: {summary['total_labels']}")
    print(f"Review sample: {summary['review_sample']}")
    print("Reasons:")
    reason_counts = summary["reason_counts"]
    for reason in REASON_ORDER:
        count = reason_counts.get(reason, 0)
        if count:
            print(f"  {reason}: {count}")
    print(f"Output: {args.out}")


if __name__ == "__main__":
    main()
