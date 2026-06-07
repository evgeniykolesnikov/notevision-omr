"""Tests for batch processing of raw document directories."""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from batch_run_pipeline import find_document_dirs, run_batch_pipeline


class BatchPipelineTests(unittest.TestCase):
    def test_empty_raw_directory_does_not_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            raw_dir = root / "raw"
            outputs_dir = root / "outputs"
            raw_dir.mkdir()

            report = run_batch_pipeline(raw_dir, outputs_dir)

            self.assertTrue(report.empty)
            self.assertTrue(
                (outputs_dir / "reports" / "batch_pipeline_report.csv").is_file()
            )
            self.assertTrue(
                (outputs_dir / "reports" / "all_page_predictions.csv").is_file()
            )

    def test_document_without_pdf_is_reported_and_batch_continues(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            raw_dir = root / "raw"
            outputs_dir = root / "outputs"
            document_dir = raw_dir / "rsl01004470876"
            document_dir.mkdir(parents=True)
            (document_dir / "01004470876.mrc").touch()

            report = run_batch_pipeline(raw_dir, outputs_dir)

            self.assertEqual(len(report), 1)
            row = report.iloc[0]
            self.assertEqual(row["doc_id"], "rsl01004470876")
            self.assertEqual(row["pdf_status"], "error")
            self.assertEqual(row["predictions_status"], "not_processed")
            self.assertIn("No PDF file found", row["error_message"])

    def test_find_document_dirs_returns_only_sorted_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            raw_dir = Path(temporary_dir)
            (raw_dir / "rsl00000000002").mkdir()
            (raw_dir / "rsl00000000001").mkdir()
            (raw_dir / "source.txt").touch()

            document_dirs = find_document_dirs(raw_dir)

            self.assertEqual(
                [path.name for path in document_dirs],
                ["rsl00000000001", "rsl00000000002"],
            )


if __name__ == "__main__":
    unittest.main()
