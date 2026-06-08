"""Build a reproducible sample of successful MXL pages for expert review."""

from __future__ import annotations

import argparse
import csv
import random
from collections import Counter
from pathlib import Path
from typing import Iterable

REQUIRED_COLUMNS = {
    "doc_id",
    "page_index",
    "page_type",
    "image_path",
    "has_music_score",
}
OUTPUT_EXTRA_COLUMNS = ["mxl_path", "selection_reason"]

REASON_MIXED = "mixed"
REASON_FAILURE_DOCUMENT = "failure_document"
REASON_LOW_CONFIDENCE = "low_confidence"
REASON_DOCUMENT_COVERAGE = "document_coverage"
REASON_RANDOM = "random_successful"
REASON_ORDER = [
    REASON_MIXED,
    REASON_FAILURE_DOCUMENT,
    REASON_LOW_CONFIDENCE,
    REASON_DOCUMENT_COVERAGE,
    REASON_RANDOM,
]


def _page_key(row: dict[str, str]) -> tuple[str, int]:
    doc_id = str(row.get("doc_id", "")).strip()
    try:
        page_index = int(float(str(row.get("page_index", "")).strip()))
    except ValueError as error:
        raise ValueError(
            f"Invalid page_index for {doc_id or '<missing>'}: "
            f"{row.get('page_index', '')}"
        ) from error
    if not doc_id or page_index < 1:
        raise ValueError(
            "OMR evaluation sample contains an empty doc_id or "
            "non-positive page_index"
        )
    return doc_id, page_index


def _score(row: dict[str, str]) -> float:
    key = _page_key(row)
    try:
        return float(str(row.get("has_music_score", "")).strip())
    except ValueError as error:
        raise ValueError(
            f"Invalid has_music_score for {key[0]}/page_{key[1]}: "
            f"{row.get('has_music_score', '')}"
        ) from error


def find_page_mxl(
    omr_dir: Path,
    doc_id: str,
    page_index: int,
) -> Path | None:
    """Return the first deterministic MXL export for one page."""
    page_dir = omr_dir / doc_id / f"page_{page_index:03d}"
    if not page_dir.is_dir():
        return None
    matches = sorted(
        page_dir.rglob("*.mxl"),
        key=lambda path: str(path).casefold(),
    )
    return matches[0] if matches else None


def inspect_omr_rows(
    rows: Iterable[dict[str, str]],
    omr_dir: Path,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Split unique OMR rows into successful MXL pages and failures."""
    if not omr_dir.is_dir():
        raise FileNotFoundError(f"OMR directory does not exist: {omr_dir}")

    successful: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []
    seen: set[tuple[str, int]] = set()
    for source_row in rows:
        row = dict(source_row)
        key = _page_key(row)
        if key in seen:
            continue
        seen.add(key)
        mxl_path = find_page_mxl(omr_dir, key[0], key[1])
        if mxl_path is None:
            failures.append(row)
        else:
            row["mxl_path"] = str(mxl_path)
            successful.append(row)
    return successful, failures


def _sample_keys(
    candidates: list[dict[str, str]],
    count: int,
    generator: random.Random,
) -> list[tuple[str, int]]:
    if count <= 0 or not candidates:
        return []
    ordered = sorted(candidates, key=_page_key)
    return [
        _page_key(row)
        for row in generator.sample(ordered, min(count, len(ordered)))
    ]


def build_omr_ground_truth_sample(
    rows: Iterable[dict[str, str]],
    omr_dir: Path,
    *,
    limit: int = 30,
    random_seed: int = 42,
    mixed_target: int = 6,
    failure_document_target: int = 10,
    low_confidence_target: int = 6,
) -> list[dict[str, str]]:
    """Select successful MXL pages using the thesis review priorities."""
    if limit <= 0:
        raise ValueError(f"limit must be positive, got: {limit}")
    for name, value in (
        ("mixed_target", mixed_target),
        ("failure_document_target", failure_document_target),
        ("low_confidence_target", low_confidence_target),
    ):
        if value < 0:
            raise ValueError(f"{name} must be non-negative, got: {value}")

    successful, failures = inspect_omr_rows(rows, omr_dir)
    if len(successful) < limit:
        raise ValueError(
            f"Only {len(successful)} pages have existing MXL files; "
            f"cannot build a sample of {limit}"
        )

    rows_by_key = {_page_key(row): row for row in successful}
    failure_docs = {_page_key(row)[0] for row in failures}
    reasons: dict[tuple[str, int], set[str]] = {}
    generator = random.Random(random_seed)

    def add_keys(keys: Iterable[tuple[str, int]], reason: str) -> None:
        for key in keys:
            if len(reasons) >= limit and key not in reasons:
                break
            reasons.setdefault(key, set()).add(reason)

    mixed = [
        row
        for row in successful
        if str(row.get("page_type", "")).strip().lower() == "mixed"
    ]
    add_keys(
        _sample_keys(mixed, mixed_target, generator),
        REASON_MIXED,
    )

    failure_document_rows = [
        row for row in successful if _page_key(row)[0] in failure_docs
    ]
    existing_failure_count = sum(
        key[0] in failure_docs for key in reasons
    )
    add_keys(
        _sample_keys(
            [
                row
                for row in failure_document_rows
                if _page_key(row) not in reasons
            ],
            failure_document_target - existing_failure_count,
            generator,
        ),
        REASON_FAILURE_DOCUMENT,
    )

    low_confidence = [row for row in successful if _score(row) < 0.95]
    existing_low_count = sum(
        _score(rows_by_key[key]) < 0.95 for key in reasons
    )
    add_keys(
        _sample_keys(
            [row for row in low_confidence if _page_key(row) not in reasons],
            low_confidence_target - existing_low_count,
            generator,
        ),
        REASON_LOW_CONFIDENCE,
    )

    all_docs = sorted({_page_key(row)[0] for row in successful})
    selected_docs = {key[0] for key in reasons}
    for doc_id in all_docs:
        if len(reasons) >= limit:
            break
        if doc_id in selected_docs:
            continue
        document_rows = [
            row
            for row in successful
            if _page_key(row)[0] == doc_id and _page_key(row) not in reasons
        ]
        keys = _sample_keys(document_rows, 1, generator)
        add_keys(keys, REASON_DOCUMENT_COVERAGE)
        selected_docs.add(doc_id)

    remaining = [
        row for row in successful if _page_key(row) not in reasons
    ]
    add_keys(
        _sample_keys(remaining, limit - len(reasons), generator),
        REASON_RANDOM,
    )

    reason_position = {
        reason: position for position, reason in enumerate(REASON_ORDER)
    }
    selected: list[dict[str, str]] = []
    for key in sorted(reasons):
        row = dict(rows_by_key[key])
        applicable = set(reasons[key])
        if str(row.get("page_type", "")).strip().lower() == "mixed":
            applicable.add(REASON_MIXED)
        if key[0] in failure_docs:
            applicable.add(REASON_FAILURE_DOCUMENT)
        if _score(row) < 0.95:
            applicable.add(REASON_LOW_CONFIDENCE)
        row["selection_reason"] = ";".join(
            sorted(applicable, key=lambda reason: reason_position[reason])
        )
        selected.append(row)
    return selected


def read_omr_eval_sample(
    path: Path,
) -> tuple[list[str], list[dict[str, str]]]:
    """Read and validate the fixed OMR evaluation sample."""
    if not path.is_file():
        raise FileNotFoundError(f"OMR evaluation sample does not exist: {path}")
    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        columns = list(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - set(columns))
        if missing:
            raise ValueError(
                "OMR evaluation sample is missing required columns: "
                + ", ".join(missing)
            )
        return columns, list(reader)


def write_omr_ground_truth_sample(
    sample_path: Path,
    omr_dir: Path,
    output_path: Path,
    *,
    limit: int = 30,
    random_seed: int = 42,
) -> dict[str, object]:
    """Build and save the expert-review source sample."""
    input_columns, rows = read_omr_eval_sample(sample_path)
    selected = build_omr_ground_truth_sample(
        rows,
        omr_dir,
        limit=limit,
        random_seed=random_seed,
    )
    output_columns = [
        column
        for column in input_columns
        if column not in OUTPUT_EXTRA_COLUMNS
    ] + OUTPUT_EXTRA_COLUMNS
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=output_columns,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(selected)

    reason_counts: Counter[str] = Counter()
    for row in selected:
        reason_counts.update(row["selection_reason"].split(";"))
    return {
        "sample_pages": len(selected),
        "documents": len({row["doc_id"] for row in selected}),
        "reason_counts": reason_counts,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--omr-sample",
        type=Path,
        default=Path("data/labels/omr_eval_sample_thesis.csv"),
    )
    parser.add_argument(
        "--omr-dir",
        type=Path,
        default=Path("outputs/omr_300dpi"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/labels/omr_ground_truth_sample_thesis.csv"),
    )
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--random-seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        summary = write_omr_ground_truth_sample(
            args.omr_sample,
            args.omr_dir,
            args.out,
            limit=args.limit,
            random_seed=args.random_seed,
        )
    except (FileNotFoundError, ValueError, OSError, csv.Error) as error:
        raise SystemExit(f"Error: {error}") from error

    print(f"Expert sample pages: {summary['sample_pages']}")
    print(f"Documents represented: {summary['documents']}")
    print("Selection reasons:")
    for reason in REASON_ORDER:
        count = summary["reason_counts"].get(reason, 0)
        if count:
            print(f"  {reason}: {count}")
    print(f"Output: {args.out}")


if __name__ == "__main__":
    main()
