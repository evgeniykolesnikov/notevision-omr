"""Tests for music page detection metrics."""

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from notevision.evaluation.metrics import evaluate_binary_predictions


class EvaluationTests(unittest.TestCase):
    def test_perfect_predictions(self) -> None:
        labels = pd.DataFrame(
            {
                "doc_id": ["doc", "doc", "doc", "doc"],
                "page_index": [1, 2, 3, 4],
                "has_music": [0, 1, 1, 0],
            }
        )
        predictions = pd.DataFrame(
            {
                "doc_id": ["doc", "doc", "doc", "doc"],
                "page_index": [1, 2, 3, 4],
                "has_music_pred": [0, 1, 1, 0],
            }
        )

        metrics = evaluate_binary_predictions(labels, predictions)

        self.assertEqual(metrics["accuracy"], 1.0)
        self.assertEqual(metrics["precision"], 1.0)
        self.assertEqual(metrics["recall"], 1.0)
        self.assertEqual(metrics["f1"], 1.0)
        self.assertEqual(
            metrics["confusion_matrix"],
            {"tn": 2, "fp": 0, "fn": 0, "tp": 2},
        )

    def test_false_positive_and_false_negative(self) -> None:
        labels = pd.DataFrame(
            {
                "doc_id": ["doc"] * 4,
                "page_index": [1, 2, 3, 4],
                "has_music": [0, 0, 1, 1],
                "page_type": ["cover", "text", "music", "music"],
            }
        )
        predictions = pd.DataFrame(
            {
                "doc_id": ["doc"] * 4,
                "page_index": [1, 2, 3, 4],
                "has_music_pred": [0, 1, 0, 1],
            }
        )

        metrics = evaluate_binary_predictions(labels, predictions)

        self.assertEqual(metrics["accuracy"], 0.5)
        self.assertEqual(metrics["precision"], 0.5)
        self.assertEqual(metrics["recall"], 0.5)
        self.assertEqual(metrics["f1"], 0.5)
        self.assertEqual(
            metrics["confusion_matrix"],
            {"tn": 1, "fp": 1, "fn": 1, "tp": 1},
        )
        self.assertEqual(
            metrics["error_analysis_by_page_type"]["text"]["fp"],
            1,
        )
        self.assertEqual(
            metrics["error_analysis_by_page_type"]["music"]["fn"],
            1,
        )

    def test_missing_prediction_raises_clear_error(self) -> None:
        labels = pd.DataFrame(
            {
                "doc_id": ["doc", "doc"],
                "page_index": [1, 2],
                "has_music": [0, 1],
            }
        )
        predictions = pd.DataFrame(
            {
                "doc_id": ["doc"],
                "page_index": [1],
                "has_music_pred": [0],
            }
        )

        with self.assertRaisesRegex(
            ValueError,
            r"Predictions are missing pages.*doc/page_2",
        ):
            evaluate_binary_predictions(labels, predictions)


if __name__ == "__main__":
    unittest.main()
