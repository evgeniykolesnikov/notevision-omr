"""Tests for baseline music page classification."""

import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from notevision.classification.features import extract_page_features
from notevision.classification.predict_pages import rule_based_has_music


class PageFeatureTests(unittest.TestCase):
    def test_extract_page_features_reads_synthetic_image(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            image_path = Path(temporary_dir) / "page.png"
            image = np.full((200, 300), 255, dtype=np.uint8)
            self.assertTrue(cv2.imwrite(str(image_path), image))

            features = extract_page_features(image_path)

            self.assertEqual(features["image_width"], 300)
            self.assertEqual(features["image_height"], 200)
            self.assertEqual(features["horizontal_line_count"], 0)

    def test_rule_based_has_music_returns_prediction_and_score(self) -> None:
        result = rule_based_has_music(
            {
                "horizontal_line_count": 5,
                "horizontal_line_density": 0.02,
                "staff_like_line_groups": 1,
            }
        )

        self.assertIn(result["has_music_pred"], (0, 1))
        self.assertIsInstance(result["has_music_score"], float)
        self.assertGreaterEqual(result["has_music_score"], 0.0)
        self.assertLessEqual(result["has_music_score"], 1.0)

    def test_staff_lines_score_higher_than_empty_page(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            empty_path = root / "empty.png"
            staff_path = root / "staff.png"
            empty = np.full((240, 400), 255, dtype=np.uint8)
            staff = empty.copy()

            for start_y in (50, 140):
                for offset in range(0, 50, 10):
                    cv2.line(
                        staff,
                        (30, start_y + offset),
                        (370, start_y + offset),
                        0,
                        1,
                    )

            self.assertTrue(cv2.imwrite(str(empty_path), empty))
            self.assertTrue(cv2.imwrite(str(staff_path), staff))

            empty_score = rule_based_has_music(
                extract_page_features(empty_path)
            )["has_music_score"]
            staff_score = rule_based_has_music(
                extract_page_features(staff_path)
            )["has_music_score"]

            self.assertGreater(staff_score, empty_score)


if __name__ == "__main__":
    unittest.main()
