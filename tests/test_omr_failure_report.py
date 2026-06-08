"""Tests for page-level OMR pipeline failure reporting."""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_omr_failure_report import build_omr_failure_rows


class OmrFailureReportTests(unittest.TestCase):
    def test_classifies_missing_mxl_before_missing_midi(self) -> None:
        rows = [
            {
                "doc_id": "doc-a",
                "page_index": 1,
                "image_path": "one.png",
                "has_mxl": False,
                "has_midi": False,
            },
            {
                "doc_id": "doc-a",
                "page_index": 2,
                "image_path": "two.png",
                "has_mxl": True,
                "has_midi": False,
            },
            {
                "doc_id": "doc-a",
                "page_index": 3,
                "image_path": "three.png",
                "has_mxl": True,
                "has_midi": True,
            },
        ]

        failures = build_omr_failure_rows(rows)

        self.assertEqual(len(failures), 2)
        self.assertEqual(failures[0]["failure_type"], "missing_mxl")
        self.assertEqual(failures[1]["failure_type"], "missing_midi")


if __name__ == "__main__":
    unittest.main()
