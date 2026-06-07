"""Tests for the OMR result summary."""

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from summarize_omr_results import summarize_omr_results


class SummarizeOmrResultsTests(unittest.TestCase):
    def test_summary_counts_rate_mxl_and_failed_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            omr_dir = root / "outputs" / "omr_300dpi"
            first_dir = omr_dir / "doc-a" / "page_001"
            second_dir = omr_dir / "doc-b" / "page_003"
            first_dir.mkdir(parents=True)
            second_dir.mkdir(parents=True)
            first_mxl = first_dir / "page_001.mxl"
            second_mxl = second_dir / "page_003.mxl"
            first_mxl.write_bytes(b"a" * 100)
            second_mxl.write_bytes(b"b" * 300)

            report = pd.DataFrame(
                {
                    "doc_id": ["doc-a", "doc-b", "doc-c"],
                    "page_index": [1, 3, 2],
                    "output_dir": [
                        str(first_dir),
                        str(second_dir),
                        str(omr_dir / "doc-c" / "page_002"),
                    ],
                    "status": ["success", "success", "failed"],
                    "message": ["", "", "Audiveris failed"],
                }
            )

            summary = summarize_omr_results(
                report,
                omr_dir,
                project_root=root,
            )

            self.assertEqual(summary["total"], 3)
            self.assertEqual(summary["success"], 2)
            self.assertEqual(summary["failed"], 1)
            self.assertAlmostEqual(summary["success_rate"], 2 / 3)
            self.assertEqual(summary["mxl_count"], 2)
            self.assertEqual(summary["mxl_size"]["min"], 100)
            self.assertEqual(summary["mxl_size"]["max"], 300)
            self.assertEqual(summary["mxl_size"]["mean"], 200.0)
            self.assertEqual(
                summary["successful_pages"][0]["mxl_path"],
                str(first_mxl),
            )
            self.assertEqual(
                summary["failed_pages"],
                [
                    {
                        "doc_id": "doc-c",
                        "page_index": 2,
                        "message": "Audiveris failed",
                    }
                ],
            )


if __name__ == "__main__":
    unittest.main()
