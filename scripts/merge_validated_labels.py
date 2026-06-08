"""Merge previous manual labels into a new thesis labeling template."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterable

KEY_COLUMNS = ["doc_id", "page_index"]
MANUAL_COLUMNS = ["page_type", "has_music", "quality_comment"]
PREDICTION_COLUMNS = ["has_music_pred", "has_music_score"]
REQUIRED_TEMPLATE_COLUMNS = [
    *KEY_COLUMNS,
    *MANUAL_COLUMNS,
    "image_path",
    *PREDICTION_COLUMNS,
]
REQUIRED_VALIDATED_COLUMNS = [*KEY_COLUMNS, *MANUAL_COLUMNS]
ADDED_COLUMNS = ["validation_source", "needs_review"]


def _validate_columns(
    columns: Iterable[str] | None,
    required: list[str],
    source_name: str,
) -> list[str]:
    actual = list(columns or [])
    missing = [column for column in required if column not in actual]
    if missing:
        raise ValueError(
            f"{source_name} CSV is missing required columns: "
            f"{', '.join(missing)}"
        )
    return actual


def _page_key(row: dict[str, str], source_name: str) -> tuple[str, str]:
    doc_id = str(row.get("doc_id", "")).strip()
    page_index = str(row.get("page_index", "")).strip()
    if not doc_id or not page_index:
        raise ValueError(
            f"{source_name} CSV contains an empty doc_id or page_index"
        )
    return doc_id, page_index


def _index_validated_rows(
    rows: Iterable[dict[str, str]],
) -> dict[tuple[str, str], dict[str, str]]:
    indexed: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        key = _page_key(row, "Validated")
        if key in indexed:
            raise ValueError(
                "Validated CSV contains duplicate page key: "
                f"{key[0]}/page_{key[1]}"
            )
        indexed[key] = row
    return indexed


def _is_uncertain(score: str) -> bool:
    try:
        numeric_score = float(score)
    except (TypeError, ValueError):
        return True
    return 0.1 <= numeric_score <= 0.9


def _is_label_disagreement(row: dict[str, str]) -> bool:
    try:
        return int(float(row["has_music"])) != int(
            float(row["has_music_pred"])
        )
    except (KeyError, TypeError, ValueError):
        return True


def merge_validated_rows(
    template_rows: Iterable[dict[str, str]],
    validated_rows: Iterable[dict[str, str]],
) -> tuple[list[dict[str, str]], int]:
    """Merge previous manual labels while keeping current predictions."""
    previous_by_key = _index_validated_rows(validated_rows)
    merged_rows: list[dict[str, str]] = []
    seen_template_keys: set[tuple[str, str]] = set()
    transferred = 0

    for template_row in template_rows:
        key = _page_key(template_row, "Template")
        if key in seen_template_keys:
            raise ValueError(
                "Template CSV contains duplicate page key: "
                f"{key[0]}/page_{key[1]}"
            )
        seen_template_keys.add(key)

        merged = dict(template_row)
        previous = previous_by_key.get(key)
        if previous is not None:
            for column in MANUAL_COLUMNS:
                merged[column] = previous.get(column, "")
            merged["validation_source"] = "manual_previous"
            transferred += 1
        else:
            merged["validation_source"] = "template_prediction"

        needs_review = merged["validation_source"] == "template_prediction"
        needs_review = needs_review or _is_uncertain(
            merged.get("has_music_score", "")
        )
        needs_review = needs_review or (
            str(merged.get("page_type", "")).strip().lower() == "unknown"
        )
        needs_review = needs_review or _is_label_disagreement(merged)
        merged["needs_review"] = "1" if needs_review else "0"
        merged_rows.append(merged)

    return merged_rows, transferred


def _read_csv(
    path: Path,
    required_columns: list[str],
    source_name: str,
) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        raise FileNotFoundError(f"{source_name} CSV does not exist: {path}")
    try:
        with path.open(encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            columns = _validate_columns(
                reader.fieldnames,
                required_columns,
                source_name,
            )
            return columns, list(reader)
    except UnicodeError as error:
        raise ValueError(
            f"Could not decode {source_name.lower()} CSV as UTF-8: {path}"
        ) from error
    except csv.Error as error:
        raise ValueError(
            f"Could not parse {source_name.lower()} CSV {path}: {error}"
        ) from error


def merge_validated_labels(
    template_path: Path,
    validated_path: Path,
    output_path: Path,
) -> dict[str, int]:
    """Merge CSV files, write the result, and return summary counts."""
    template_columns, template_rows = _read_csv(
        template_path,
        REQUIRED_TEMPLATE_COLUMNS,
        "Template",
    )
    _, validated_rows = _read_csv(
        validated_path,
        REQUIRED_VALIDATED_COLUMNS,
        "Validated",
    )
    merged_rows, transferred = merge_validated_rows(
        template_rows,
        validated_rows,
    )

    output_columns = [
        column for column in template_columns if column not in ADDED_COLUMNS
    ] + ADDED_COLUMNS
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=output_columns,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(merged_rows)

    return {
        "template_rows": len(template_rows),
        "validated_rows": len(validated_rows),
        "transferred": transferred,
        "needs_review": sum(
            row["needs_review"] == "1" for row in merged_rows
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--validated", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        summary = merge_validated_labels(
            args.template,
            args.validated,
            args.out,
        )
    except (FileNotFoundError, ValueError, OSError) as error:
        raise SystemExit(f"Error: {error}") from error

    print(f"Template rows: {summary['template_rows']}")
    print(f"Previous validated rows: {summary['validated_rows']}")
    print(f"Manual labels transferred: {summary['transferred']}")
    print(f"Needs review: {summary['needs_review']}")
    print(f"Output: {args.out}")


if __name__ == "__main__":
    main()
