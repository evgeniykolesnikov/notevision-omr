"""Tests for safe review result file discovery."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from review_app.media_files import download_filename, find_review_result_file


class ReviewMediaFilesTests(unittest.TestCase):
    def test_finds_midi_and_mxl_in_project_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package_dir = root / "package"
            package_dir.mkdir()
            midi = root / "outputs" / "midi" / "rsl001" / "page_007.mid"
            mxl = (
                root
                / "outputs"
                / "omr_300dpi"
                / "rsl001"
                / "page_007"
                / "page_007.mxl"
            )
            midi.parent.mkdir(parents=True)
            mxl.parent.mkdir(parents=True)
            midi.write_bytes(b"midi")
            mxl.write_bytes(b"mxl")
            item = {
                "doc_id": "rsl001",
                "page_index": 7,
                "scan_path": "01_rsl001_page_007_scan.png",
            }

            self.assertEqual(
                find_review_result_file(
                    item,
                    kind="midi",
                    package_dir=package_dir,
                    project_root=root,
                ),
                midi.resolve(),
            )
            self.assertEqual(
                find_review_result_file(
                    item,
                    kind="mxl",
                    package_dir=package_dir,
                    project_root=root,
                ),
                mxl.resolve(),
            )
            self.assertEqual(
                download_filename(item, "midi"),
                "notevision_rsl001_page_007.mid",
            )

    def test_missing_or_invalid_item_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package_dir = root / "package"
            package_dir.mkdir()
            self.assertIsNone(
                find_review_result_file(
                    {"doc_id": "../../escape", "page_index": 1},
                    kind="midi",
                    package_dir=package_dir,
                    project_root=root,
                )
            )


if __name__ == "__main__":
    unittest.main()
