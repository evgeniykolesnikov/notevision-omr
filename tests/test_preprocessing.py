"""Tests for music page preprocessing."""

import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from notevision.preprocessing.music_pages import (
    preprocess_music_pages,
    preprocess_page,
)


class MusicPagePreprocessingTests(unittest.TestCase):
    def test_preprocess_page_creates_output_image(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            source = root / "page.png"
            destination = root / "output" / "page_001_binary.png"
            image = np.full((120, 180), 240, dtype=np.uint8)
            cv2.line(image, (10, 50), (170, 50), 20, 2)
            self.assertTrue(cv2.imwrite(str(source), image))

            result = preprocess_page(source, destination)

            self.assertEqual(result, destination)
            self.assertTrue(destination.is_file())
            output = cv2.imread(str(destination), cv2.IMREAD_GRAYSCALE)
            self.assertIsNotNone(output)
            self.assertTrue(set(np.unique(output)).issubset({0, 255}))

    def test_batch_processes_only_music_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            first = root / "page_001.png"
            second = root / "page_002.png"
            image = np.full((80, 100), 255, dtype=np.uint8)
            self.assertTrue(cv2.imwrite(str(first), image))
            self.assertTrue(cv2.imwrite(str(second), image))
            labels = pd.DataFrame(
                {
                    "doc_id": ["doc", "doc"],
                    "page_index": [1, 2],
                    "image_path": [str(first), str(second)],
                    "has_music": [1, 0],
                }
            )

            report = preprocess_music_pages(labels, root / "preprocessed")

            self.assertEqual(len(report), 1)
            self.assertEqual(report.iloc[0]["page_index"], 1)
            self.assertTrue(
                (root / "preprocessed" / "doc" / "page_001_binary.png").is_file()
            )
            self.assertFalse(
                (root / "preprocessed" / "doc" / "page_002_binary.png").exists()
            )

    def test_missing_page_is_reported_without_stopping_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            valid = root / "page_001.png"
            missing = root / "missing.png"
            image = np.full((80, 100), 255, dtype=np.uint8)
            self.assertTrue(cv2.imwrite(str(valid), image))
            labels = pd.DataFrame(
                {
                    "doc_id": ["doc", "doc"],
                    "page_index": [1, 2],
                    "image_path": [str(missing), str(valid)],
                    "has_music": [1, 1],
                }
            )

            report = preprocess_music_pages(labels, root / "preprocessed")

            self.assertEqual(report["status"].tolist(), ["error", "success"])
            self.assertIn(
                "Page image does not exist",
                report.iloc[0]["message"],
            )
            self.assertTrue(
                (root / "preprocessed" / "doc" / "page_002_binary.png").is_file()
            )


if __name__ == "__main__":
    unittest.main()
