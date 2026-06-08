"""Build a compact priority sample for thesis manual review."""

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
    "review_reason",
]
PRIORITY_GROUP_COLUMN = "priority_group"

REASON_UNKNOWN = "unknown"
REASON_UNCERTAIN = "uncertain_score"
REASON_HIGH_NON_MUSIC = "high_score_non_music"
REASON_LOW_MUSIC = "low_confidence_music"
REASON_FIRST = "first_2_pages"
REASON_LAST = "last_2_pages"
REASON_RANDOM_MUSIC = "random_confident_music"

GROUP_BOUNDARY = "boundary_pages"
GROUP_UNCERTAIN = "uncertain"
GROUP_UNKNOWN = "unknown"
GROUP_RANDOM_MUSIC = "random_confident_music"

GROUP_ORDER = [
    GROUP_BOUNDARY,
    GROUP_UNCERTAIN,
    GROUP_UNKNOWN,
    GROUP_RANDOM_MUSIC,
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
            "Review sample contains an empty doc_id or non-positive page_index"
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


def _reasons(row: dict[str, str]) -> set[str]:
    return {
        reason.strip()
        for reason in str(row.get("review_reason", "")).split(";")
        if reason.strip()
    }


def _unique_rows(
    rows: Iterable[dict[str, str]],
) -> dict[tuple[str, int], dict[str, str]]:
    unique: dict[tuple[str, int], dict[str, str]] = {}
    for row in rows:
        unique.setdefault(_page_key(row), dict(row))
    return unique


def build_thesis_review_priority(
    review_rows: Iterable[dict[str, str]],
    *,
    random_confident_music: int = 100,
    random_seed: int = 42,
) -> list[dict[str, str]]:
    """Select priority review pages and attach applicable groups."""
    if random_confident_music < 0:
        raise ValueError(
            "random_confident_music must be zero or positive, got: "
            f"{random_confident_music}"
        )

    rows_by_key = _unique_rows(review_rows)
    groups: defaultdict[tuple[str, int], set[str]] = defaultdict(set)
    random_candidates: list[tuple[str, int]] = []

    for key, row in rows_by_key.items():
        reasons = _reasons(row)

        if REASON_FIRST in reasons or REASON_LAST in reasons:
            groups[key].add(GROUP_BOUNDARY)
        if reasons.intersection(
            {
                REASON_UNCERTAIN,
                REASON_HIGH_NON_MUSIC,
                REASON_LOW_MUSIC,
            }
        ):
            groups[key].add(GROUP_UNCERTAIN)
        if REASON_UNKNOWN in reasons:
            groups[key].add(GROUP_UNKNOWN)

        is_confident_music = _prediction(row) == 1 and _score(row) >= 0.95
        if REASON_RANDOM_MUSIC in reasons or is_confident_music:
            random_candidates.append(key)

    random_candidates.sort(key=lambda key: (key[0], key[1]))
    sample_size = min(random_confident_music, len(random_candidates))
    generator = random.Random(random_seed)
    for key in generator.sample(random_candidates, sample_size):
        groups[key].add(GROUP_RANDOM_MUSIC)

    group_position = {
        group: position for position, group in enumerate(GROUP_ORDER)
    }
    selected: list[dict[str, str]] = []
    for key in sorted(groups, key=lambda item: (item[0], item[1])):
        if not groups[key]:
            continue
        row = dict(rows_by_key[key])
        row[PRIORITY_GROUP_COLUMN] = ";".join(
            sorted(
                groups[key],
                key=lambda group: group_position[group],
            )
        )
        selected.append(row)
    return selected


def _read_review_sample(
    path: Path,
) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        raise FileNotFoundError(f"Review sample CSV does not exist: {path}")
    try:
        with path.open(encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            columns = list(reader.fieldnames or [])
            missing = [
                column for column in REQUIRED_COLUMNS if column not in columns
            ]
            if missing:
                raise ValueError(
                    "Review sample CSV is missing required columns: "
                    + ", ".join(missing)
                )
            return columns, list(reader)
    except UnicodeError as error:
        raise ValueError(
            f"Could not decode review sample CSV as UTF-8: {path}"
        ) from error
    except csv.Error as error:
        raise ValueError(
            f"Could not parse review sample CSV {path}: {error}"
        ) from error


def write_thesis_review_priority(
    review_sample_path: Path,
    output_path: Path,
    *,
    random_confident_music: int = 100,
    random_seed: int = 42,
) -> dict[str, object]:
    """Read the review sample, write priority rows, and return summary."""
    input_columns, review_rows = _read_review_sample(review_sample_path)
    priority_rows = build_thesis_review_priority(
        review_rows,
        random_confident_music=random_confident_music,
        random_seed=random_seed,
    )
    output_columns = [
        column for column in input_columns if column != PRIORITY_GROUP_COLUMN
    ] + [PRIORITY_GROUP_COLUMN]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=output_columns,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(priority_rows)

    group_counts: Counter[str] = Counter()
    for row in priority_rows:
        group_counts.update(row[PRIORITY_GROUP_COLUMN].split(";"))

    return {
        "review_sample_input": len(review_rows),
        "priority_sample": len(priority_rows),
        "group_counts": group_counts,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-sample", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--random-confident-music", type=int, default=100)
    parser.add_argument("--random-seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        summary = write_thesis_review_priority(
            args.review_sample,
            args.out,
            random_confident_music=args.random_confident_music,
            random_seed=args.random_seed,
        )
    except (FileNotFoundError, ValueError, OSError) as error:
        raise SystemExit(f"Error: {error}") from error

    print(f"Review sample input: {summary['review_sample_input']}")
    print(f"Priority sample: {summary['priority_sample']}")
    print("Priority groups:")
    group_counts = summary["group_counts"]
    for group in GROUP_ORDER:
        count = group_counts.get(group, 0)
        if count:
            print(f"  {group}: {count}")
    print(f"Output: {args.out}")


if __name__ == "__main__":
    main()
