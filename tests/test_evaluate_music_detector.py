"""Tests for thesis music detector metrics."""

import csv
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from evaluate_music_detector import (
    METRICS_COLUMNS,
    evaluate_music_detector_rows,
    write_music_detector_metrics,
)


class EvaluateMusicDetectorTests(unittest.TestCase):
    def test_calculates_confusion_matrix_and_metrics(self) -> None:
        rows = [
            {"has_music": "1", "has_music_pred": "1"},
            {"has_music": "1", "has_music_pred": "0"},
            {"has_music": "0", "has_music_pred": "1"},
            {"has_music": "0", "has_music_pred": "0"},
        ]

        metrics = evaluate_music_detector_rows(rows)

        self.assertEqual(metrics["tp"], 1)
        self.assertEqual(metrics["fp"], 1)
        self.assertEqual(metrics["tn"], 1)
        self.assertEqual(metrics["fn"], 1)
        self.assertEqual(metrics["accuracy"], 0.5)
        self.assertEqual(metrics["precision"], 0.5)
        self.assertEqual(metrics["recall"], 0.5)
        self.assertEqual(metrics["f1"], 0.5)

    def test_zero_denominators_return_zero(self) -> None:
        metrics = evaluate_music_detector_rows(
            [{"has_music": "0", "has_music_pred": "0"}]
        )

        self.assertEqual(metrics["precision"], 0.0)
        self.assertEqual(metrics["recall"], 0.0)
        self.assertEqual(metrics["f1"], 0.0)

    def test_writes_expected_csv_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            labels_path = root / "labels.csv"
            output_path = root / "metrics.csv"
            with labels_path.open("w", encoding="utf-8", newline="") as csv_file:
                writer = csv.DictWriter(
                    csv_file,
                    fieldnames=["has_music", "has_music_pred"],
                )
                writer.writeheader()
                writer.writerow({"has_music": 1, "has_music_pred": 1})

            write_music_detector_metrics(labels_path, output_path)
            with output_path.open(encoding="utf-8", newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                rows = list(reader)

            self.assertEqual(reader.fieldnames, METRICS_COLUMNS)
            self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
