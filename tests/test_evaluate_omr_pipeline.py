"""Tests for page and document-level OMR pipeline evaluation."""

import csv
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from evaluate_omr_pipeline import (
    REPORT_COLUMNS,
    build_omr_evaluation_markdown,
    build_omr_pipeline_rows,
    inspect_omr_sample_pages,
    write_omr_pipeline_report,
)


class EvaluateOmrPipelineTests(unittest.TestCase):
    def test_detects_mxl_midi_and_builds_document_rates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            omr_dir = root / "omr"
            midi_dir = root / "midi"
            page_dir = omr_dir / "doc-a" / "page_001"
            page_dir.mkdir(parents=True)
            (page_dir / "page_001.mxl").write_bytes(b"mxl")
            (midi_dir / "doc-a").mkdir(parents=True)
            (midi_dir / "doc-a" / "page_001.mid").write_bytes(b"midi")
            rows = [
                {"doc_id": "doc-a", "page_index": "1", "image_path": "one.png"},
                {"doc_id": "doc-a", "page_index": "2", "image_path": "two.png"},
            ]

            inspected = inspect_omr_sample_pages(rows, omr_dir, midi_dir)
            report = build_omr_pipeline_rows(inspected)[0]

            self.assertTrue(inspected[0]["has_mxl"])
            self.assertTrue(inspected[0]["has_midi"])
            self.assertFalse(inspected[1]["has_mxl"])
            self.assertEqual(report["sampled_pages"], 2)
            self.assertEqual(report["mxl_generated_pages"], 1)
            self.assertEqual(report["midi_generated_pages"], 1)
            self.assertEqual(report["mxl_success_rate"], 0.5)
            self.assertEqual(report["midi_success_rate"], 0.5)

    def test_writes_expected_report_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            sample_path = root / "sample.csv"
            output_path = root / "report.csv"
            with sample_path.open("w", encoding="utf-8", newline="") as csv_file:
                writer = csv.DictWriter(
                    csv_file,
                    fieldnames=["doc_id", "page_index", "image_path"],
                )
                writer.writeheader()
                writer.writerow(
                    {"doc_id": "doc-a", "page_index": 1, "image_path": "one.png"}
                )

            write_omr_pipeline_report(
                sample_path,
                root / "omr",
                root / "midi",
                output_path,
            )
            with output_path.open(encoding="utf-8", newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                list(reader)

            self.assertEqual(reader.fieldnames, REPORT_COLUMNS)

    def test_markdown_uses_real_counts(self) -> None:
        pages = [
            {"doc_id": "doc-a", "page_index": 1, "has_mxl": True, "has_midi": False},
            {"doc_id": "doc-a", "page_index": 2, "has_mxl": False, "has_midi": False},
        ]
        documents = build_omr_pipeline_rows(pages)

        report = build_omr_evaluation_markdown(pages, documents)

        self.assertIn("**2 страниц**", report)
        self.assertIn("| Страницы с MXL | 1 |", report)
        self.assertIn("| Страницы с MIDI | 0 |", report)
        self.assertIn("missing_mxl", report)
        self.assertIn("missing_midi", report)


if __name__ == "__main__":
    unittest.main()
