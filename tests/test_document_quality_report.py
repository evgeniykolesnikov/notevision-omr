"""Tests for per-document corpus quality reporting."""

import csv
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_document_quality_report import (
    REPORT_COLUMNS,
    build_document_quality_rows,
    write_document_quality_report,
)


class DocumentQualityReportTests(unittest.TestCase):
    def test_counts_page_types_and_comment_markers(self) -> None:
        rows = [
            {
                "doc_id": "doc-a",
                "page_type": "music",
                "has_music": "1",
                "quality_comment": "handwritten manuscript",
            },
            {
                "doc_id": "doc-a",
                "page_type": "title",
                "has_music": "0",
                "quality_comment": "photo scan with Kodak Color Control Patch",
            },
            {
                "doc_id": "doc-a",
                "page_type": "blank",
                "has_music": "0",
                "quality_comment": "",
            },
            {
                "doc_id": "doc-a",
                "page_type": "bad_scan",
                "has_music": "0",
                "quality_comment": "photographed page",
            },
            {
                "doc_id": "doc-a",
                "page_type": "unknown",
                "has_music": "0",
                "quality_comment": "",
            },
        ]

        report = build_document_quality_rows(rows)[0]

        self.assertEqual(report["total_pages"], 5)
        self.assertEqual(report["music_pages"], 1)
        self.assertEqual(report["title_pages"], 1)
        self.assertEqual(report["blank_pages"], 1)
        self.assertEqual(report["bad_scan_pages"], 1)
        self.assertEqual(report["unknown_pages"], 1)
        self.assertEqual(report["photo_scan_like"], 2)
        self.assertEqual(report["handwritten_music_like"], 1)

    def test_output_csv_has_expected_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            labels_path = root / "labels.csv"
            output_path = root / "quality.csv"
            with labels_path.open("w", encoding="utf-8", newline="") as csv_file:
                writer = csv.DictWriter(
                    csv_file,
                    fieldnames=[
                        "doc_id",
                        "page_type",
                        "has_music",
                        "quality_comment",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "doc_id": "doc-a",
                        "page_type": "text",
                        "has_music": "0",
                        "quality_comment": "",
                    }
                )

            write_document_quality_report(labels_path, output_path)
            with output_path.open(encoding="utf-8", newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                list(reader)

            self.assertEqual(reader.fieldnames, REPORT_COLUMNS)


if __name__ == "__main__":
    unittest.main()
