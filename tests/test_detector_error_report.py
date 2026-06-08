"""Tests for per-document detector error reporting."""

import csv
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_detector_error_report import (
    REPORT_COLUMNS,
    build_detector_error_rows,
    write_detector_error_report,
)


class DetectorErrorReportTests(unittest.TestCase):
    def test_counts_errors_and_quality_rates(self) -> None:
        rows = [
            {
                "doc_id": "doc-a",
                "page_index": "1",
                "page_type": "music",
                "has_music": "1",
                "has_music_pred": "1",
            },
            {
                "doc_id": "doc-a",
                "page_index": "2",
                "page_type": "unknown",
                "has_music": "0",
                "has_music_pred": "1",
            },
            {
                "doc_id": "doc-a",
                "page_index": "3",
                "page_type": "bad_scan",
                "has_music": "1",
                "has_music_pred": "0",
            },
            {
                "doc_id": "doc-a",
                "page_index": "4",
                "page_type": "text",
                "has_music": "0",
                "has_music_pred": "0",
            },
        ]

        report = build_detector_error_rows(rows)[0]

        self.assertEqual(report["detector_music_pages"], 2)
        self.assertEqual(report["validated_music_pages"], 2)
        self.assertEqual(report["false_music"], 1)
        self.assertEqual(report["false_non_music"], 1)
        self.assertEqual(report["unknown_rate"], 0.25)
        self.assertEqual(report["bad_scan_rate"], 0.25)

    def test_rows_are_ordered_by_total_errors(self) -> None:
        rows = [
            {
                "doc_id": "doc-low",
                "page_index": "1",
                "page_type": "music",
                "has_music": "1",
                "has_music_pred": "1",
            },
            {
                "doc_id": "doc-high",
                "page_index": "1",
                "page_type": "text",
                "has_music": "0",
                "has_music_pred": "1",
            },
        ]

        report = build_detector_error_rows(rows)

        self.assertEqual([row["doc_id"] for row in report], ["doc-high", "doc-low"])

    def test_output_csv_has_expected_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            labels_path = root / "labels.csv"
            output_path = root / "errors.csv"
            with labels_path.open("w", encoding="utf-8", newline="") as csv_file:
                writer = csv.DictWriter(
                    csv_file,
                    fieldnames=[
                        "doc_id",
                        "page_index",
                        "page_type",
                        "has_music",
                        "has_music_pred",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "doc_id": "doc-a",
                        "page_index": "1",
                        "page_type": "music",
                        "has_music": "1",
                        "has_music_pred": "1",
                    }
                )

            write_detector_error_report(labels_path, output_path)
            with output_path.open(encoding="utf-8", newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                list(reader)

            self.assertEqual(reader.fieldnames, REPORT_COLUMNS)


if __name__ == "__main__":
    unittest.main()
