"""Build a page-level failure report for the thesis OMR sample."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterable

from evaluate_omr_pipeline import inspect_omr_sample_pages, read_omr_sample

FAILURE_COLUMNS = [
    "doc_id",
    "page_index",
    "image_path",
    "has_mxl",
    "has_midi",
    "failure_type",
]


def build_omr_failure_rows(
    inspected_pages: Iterable[dict[str, object]],
) -> list[dict[str, object]]:
    """Return one failure row per page at the earliest missing pipeline stage."""
    failures: list[dict[str, object]] = []
    for row in inspected_pages:
        has_mxl = bool(row["has_mxl"])
        has_midi = bool(row["has_midi"])
        if has_mxl and has_midi:
            continue
        failures.append(
            {
                "doc_id": row["doc_id"],
                "page_index": int(row["page_index"]),
                "image_path": row.get("image_path", ""),
                "has_mxl": has_mxl,
                "has_midi": has_midi,
                "failure_type": "missing_mxl" if not has_mxl else "missing_midi",
            }
        )
    return sorted(
        failures,
        key=lambda row: (str(row["doc_id"]), int(row["page_index"])),
    )


def write_omr_failure_report(
    sample_path: Path,
    omr_dir: Path,
    midi_dir: Path,
    output_path: Path,
) -> list[dict[str, object]]:
    """Inspect sample pages and save all missing-artifact failures."""
    inspected = inspect_omr_sample_pages(
        read_omr_sample(sample_path),
        omr_dir,
        midi_dir,
    )
    failures = build_omr_failure_rows(inspected)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FAILURE_COLUMNS)
        writer.writeheader()
        writer.writerows(failures)
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample",
        type=Path,
        default=Path("data/labels/omr_eval_sample_thesis.csv"),
    )
    parser.add_argument(
        "--omr-dir",
        type=Path,
        default=Path("outputs/omr_300dpi"),
    )
    parser.add_argument(
        "--midi-dir",
        type=Path,
        default=Path("outputs/midi"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("outputs/reports/omr_failure_report.csv"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        failures = write_omr_failure_report(
            args.sample,
            args.omr_dir,
            args.midi_dir,
            args.out,
        )
    except (FileNotFoundError, ValueError, OSError, csv.Error) as error:
        raise SystemExit(f"Error: {error}") from error

    missing_mxl = sum(row["failure_type"] == "missing_mxl" for row in failures)
    missing_midi = len(failures) - missing_mxl
    print(f"Failed pages: {len(failures)}")
    print(f"Missing MXL: {missing_mxl}")
    print(f"Missing MIDI: {missing_midi}")
    print(f"Report: {args.out}")


if __name__ == "__main__":
    main()
