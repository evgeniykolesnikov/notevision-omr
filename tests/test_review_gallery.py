"""Tests for the manual label review gallery."""

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_review_gallery import write_review_gallery


class ReviewGalleryTests(unittest.TestCase):
    def test_gallery_contains_page_metadata_and_relative_image_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            labels_path = root / "data" / "labels.csv"
            output_path = root / "outputs" / "reports" / "gallery.html"
            labels_path.parent.mkdir(parents=True)

            pd.DataFrame(
                {
                    "doc_id": ["rsl01004470876"],
                    "page_index": [7],
                    "page_type": ["music"],
                    "has_music": [1],
                    "has_music_pred": [1],
                    "has_music_score": [0.95],
                    "image_path": [
                        "outputs/pages/rsl01004470876/page_007.png"
                    ],
                }
            ).to_csv(labels_path, index=False)

            page_count = write_review_gallery(
                labels_path,
                output_path,
                project_root=root,
            )

            self.assertEqual(page_count, 1)
            self.assertTrue(output_path.is_file())
            gallery = output_path.read_text(encoding="utf-8")
            self.assertIn("rsl01004470876", gallery)
            self.assertIn(">7<", gallery)
            self.assertIn(
                "../pages/rsl01004470876/page_007.png",
                gallery,
            )


if __name__ == "__main__":
    unittest.main()
