"""Apply exported manual corrections to a labels CSV."""

from __future__ import annotations

import argparse
import csv
import os
import tempfile
from pathlib import Path
from typing import Iterable

KEY_COLUMNS = ["doc_id", "page_index"]
CORRECTION_COLUMNS = [
    *KEY_COLUMNS,
    "page_type",
    "has_music",
    "quality_comment",
]
REQUIRED_LABEL_COLUMNS = [
    *KEY_COLUMNS,
    "page_type",
    "has_music",
    "quality_comment",
    "validation_source",
    "needs_review",
]
ALLOWED_PAGE_TYPES = {
    "music",
    "title",
    "text",
    "blank",
    "unknown",
    "mixed",
    "bad_scan",
}


def _key(row: dict[str, str], source_name: str) -> tuple[str, str]:
    doc_id = str(row.get("doc_id", "")).strip()
    page_index = str(row.get("page_index", "")).strip()
    if not doc_id or not page_index:
        raise ValueError(
            f"{source_name} CSV contains an empty doc_id or page_index"
        )
    return doc_id, page_index


def _read_csv(
    path: Path,
    required_columns: Iterable[str],
    source_name: str,
) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        raise FileNotFoundError(f"{source_name} CSV does not exist: {path}")
    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        columns = list(reader.fieldnames or [])
        missing = [column for column in required_columns if column not in columns]
        if missing:
            raise ValueError(
                f"{source_name} CSV is missing required columns: "
                + ", ".join(missing)
            )
        return columns, list(reader)


def apply_correction_rows(
    labels_rows: list[dict[str, str]],
    correction_rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], int, list[str]]:
    """Apply known corrections and return rows, count, and warning messages."""
    labels_by_key: dict[tuple[str, str], dict[str, str]] = {}
    for row in labels_rows:
        key = _key(row, "Labels")
        if key in labels_by_key:
            raise ValueError(
                f"Labels CSV contains duplicate page key: {key[0]}/page_{key[1]}"
            )
        labels_by_key[key] = row

    seen_corrections: set[tuple[str, str]] = set()
    applied = 0
    warnings: list[str] = []
    for correction in correction_rows:
        key = _key(correction, "Corrections")
        if key in seen_corrections:
            raise ValueError(
                "Corrections CSV contains duplicate page key: "
                f"{key[0]}/page_{key[1]}"
            )
        seen_corrections.add(key)

        target = labels_by_key.get(key)
        if target is None:
            warnings.append(f"Unknown page: {key[0]}/page_{key[1]}")
            continue

        page_type = correction["page_type"].strip()
        has_music = correction["has_music"].strip()
        if page_type not in ALLOWED_PAGE_TYPES:
            raise ValueError(
                f"Invalid page_type for {key[0]}/page_{key[1]}: {page_type}"
            )
        if has_music not in {"0", "1"}:
            raise ValueError(
                f"has_music must be 0 or 1 for "
                f"{key[0]}/page_{key[1]}: {has_music}"
            )

        target["page_type"] = page_type
        target["has_music"] = has_music
        target["quality_comment"] = correction["quality_comment"]
        target["validation_source"] = "manual_thesis"
        target["needs_review"] = "0"
        applied += 1

    return labels_rows, applied, warnings


def _atomic_write_csv(
    output_path: Path,
    columns: list[str],
    rows: list[dict[str, str]],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=output_path.parent,
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(
            file_descriptor,
            "w",
            encoding="utf-8",
            newline="",
        ) as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=columns,
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary_path, output_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def apply_label_corrections(
    labels_path: Path,
    corrections_path: Path,
    output_path: Path,
) -> dict[str, object]:
    """Apply a corrections CSV and safely write the resulting labels."""
    labels_columns, labels_rows = _read_csv(
        labels_path,
        REQUIRED_LABEL_COLUMNS,
        "Labels",
    )
    _, correction_rows = _read_csv(
        corrections_path,
        CORRECTION_COLUMNS,
        "Corrections",
    )
    updated_rows, applied, warnings = apply_correction_rows(
        labels_rows,
        correction_rows,
    )
    _atomic_write_csv(output_path, labels_columns, updated_rows)
    return {
        "labels_rows": len(labels_rows),
        "corrections_rows": len(correction_rows),
        "applied": applied,
        "warnings": warnings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--corrections", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        summary = apply_label_corrections(
            args.labels,
            args.corrections,
            args.out,
        )
    except (FileNotFoundError, ValueError, OSError, csv.Error) as error:
        raise SystemExit(f"Error: {error}") from error

    print(f"Labels rows: {summary['labels_rows']}")
    print(f"Corrections rows: {summary['corrections_rows']}")
    print(f"Applied: {summary['applied']}")
    print(f"Warnings: {len(summary['warnings'])}")
    for warning in summary["warnings"]:
        print(f"  Warning: {warning}")
    print(f"Output: {args.out}")


if __name__ == "__main__":
    main()
