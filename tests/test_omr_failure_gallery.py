"""Tests for the static OMR pipeline failure gallery."""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_omr_failure_gallery import build_omr_failure_gallery_html


class OmrFailureGalleryTests(unittest.TestCase):
    def test_gallery_contains_page_status_and_failure_filters(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            output_path = root / "outputs" / "reports" / "gallery.html"
            rows = [
                {
                    "doc_id": "doc-a",
                    "page_index": 2,
                    "image_path": "outputs/pages/doc-a/page_002.png",
                    "has_mxl": "True",
                    "has_midi": "False",
                    "failure_type": "missing_midi",
                }
            ]

            gallery = build_omr_failure_gallery_html(
                rows,
                output_path,
                project_root=root,
            )

            self.assertIn("doc-a", gallery)
            self.assertIn("page_002", gallery)
            self.assertIn("missing_midi", gallery)
            self.assertIn("Missing MXL", gallery)
            self.assertIn("Missing MIDI", gallery)
            self.assertIn("../pages/doc-a/page_002.png", gallery)


if __name__ == "__main__":
    unittest.main()
