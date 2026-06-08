"""Tests for detector error analysis and its static gallery."""

import csv
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_error_analysis import (
    ERROR_COLUMNS,
    build_error_gallery_html,
    build_error_rows,
    write_error_analysis,
)


class ErrorAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [
            {
                "doc_id": "doc-a",
                "page_index": "1",
                "image_path": "outputs/pages/doc-a/page_001.png",
                "has_music": "1",
                "has_music_pred": "1",
                "has_music_score": "0.98",
            },
            {
                "doc_id": "doc-a",
                "page_index": "2",
                "image_path": "outputs/pages/doc-a/page_002.png",
                "has_music": "0",
                "has_music_pred": "1",
                "has_music_score": "0.91",
            },
            {
                "doc_id": "doc-b",
                "page_index": "3",
                "image_path": "outputs/pages/doc-b/page_003.png",
                "has_music": "1",
                "has_music_pred": "0",
                "has_music_score": "0.08",
            },
        ]

    def test_returns_only_false_positives_and_false_negatives(self) -> None:
        errors = build_error_rows(self.rows)

        self.assertEqual(len(errors), 2)
        self.assertEqual(
            {row["error_type"] for row in errors},
            {"false_positive", "false_negative"},
        )

    def test_writes_expected_error_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            labels_path = root / "labels.csv"
            output_path = root / "errors.csv"
            with labels_path.open("w", encoding="utf-8", newline="") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=list(self.rows[0]))
                writer.writeheader()
                writer.writerows(self.rows)

            write_error_analysis(labels_path, output_path)
            with output_path.open(encoding="utf-8", newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                list(reader)

            self.assertEqual(reader.fieldnames, ERROR_COLUMNS)

    def test_gallery_has_error_filters_sort_and_relative_images(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            gallery_path = root / "outputs" / "reports" / "errors.html"
            html_text = build_error_gallery_html(
                build_error_rows(self.rows),
                gallery_path,
                project_root=root,
            )

            self.assertIn("False positives", html_text)
            self.assertIn("False negatives", html_text)
            self.assertIn("Sort by confidence", html_text)
            self.assertIn("../pages/doc-a/page_002.png", html_text)
            self.assertNotIn("page_001.png", html_text)


if __name__ == "__main__":
    unittest.main()
