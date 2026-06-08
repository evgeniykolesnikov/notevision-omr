"""Tests for detector metrics grouped by validation source."""

import csv
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from evaluate_detector_by_validation_source import (
    GROUP_ALL,
    GROUP_MANUAL_ALL,
    GROUP_MANUAL_PREVIOUS,
    GROUP_MANUAL_THESIS,
    GROUP_TEMPLATE,
    REPORT_COLUMNS,
    build_validation_bias_markdown,
    evaluate_detector_by_validation_source,
    write_validation_source_report,
)


class DetectorValidationSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [
            {
                "validation_source": "manual_previous",
                "has_music": "1",
                "has_music_pred": "1",
            },
            {
                "validation_source": "manual_previous",
                "has_music": "0",
                "has_music_pred": "1",
            },
            {
                "validation_source": "manual_thesis",
                "has_music": "1",
                "has_music_pred": "0",
            },
            {
                "validation_source": "manual_thesis",
                "has_music": "0",
                "has_music_pred": "0",
            },
            {
                "validation_source": "template_prediction",
                "has_music": "1",
                "has_music_pred": "1",
            },
            {
                "validation_source": "template_prediction",
                "has_music": "0",
                "has_music_pred": "0",
            },
        ]

    def test_calculates_all_required_groups(self) -> None:
        report = evaluate_detector_by_validation_source(self.rows)
        groups = {row["group"]: row for row in report}

        self.assertEqual(
            set(groups),
            {
                GROUP_MANUAL_PREVIOUS,
                GROUP_MANUAL_THESIS,
                GROUP_MANUAL_ALL,
                GROUP_TEMPLATE,
                GROUP_ALL,
            },
        )
        self.assertEqual(groups[GROUP_MANUAL_ALL]["rows"], 4)
        self.assertEqual(groups[GROUP_MANUAL_ALL]["tp"], 1)
        self.assertEqual(groups[GROUP_MANUAL_ALL]["fp"], 1)
        self.assertEqual(groups[GROUP_MANUAL_ALL]["tn"], 1)
        self.assertEqual(groups[GROUP_MANUAL_ALL]["fn"], 1)
        self.assertEqual(groups[GROUP_TEMPLATE]["f1"], 1.0)

    def test_all_f1_is_higher_than_manual_f1_with_perfect_templates(self) -> None:
        report = evaluate_detector_by_validation_source(self.rows)
        groups = {row["group"]: row for row in report}

        self.assertGreater(
            float(groups[GROUP_ALL]["f1"]),
            float(groups[GROUP_MANUAL_ALL]["f1"]),
        )

    def test_markdown_contains_bias_comparison_and_recommendations(self) -> None:
        report = evaluate_detector_by_validation_source(self.rows)

        markdown = build_validation_bias_markdown(
            report,
            Path("labels.csv"),
        )

        self.assertIn("F1 на всём корпусе", markdown)
        self.assertIn("F1 только на ручных метках", markdown)
        self.assertIn("circular evaluation", markdown)
        self.assertIn("document-level split", markdown)

    def test_writes_expected_csv_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            labels_path = root / "labels.csv"
            output_path = root / "metrics.csv"
            with labels_path.open("w", encoding="utf-8", newline="") as csv_file:
                writer = csv.DictWriter(
                    csv_file,
                    fieldnames=[
                        "validation_source",
                        "has_music",
                        "has_music_pred",
                    ],
                )
                writer.writeheader()
                writer.writerows(self.rows)

            write_validation_source_report(labels_path, output_path)
            with output_path.open(encoding="utf-8", newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                rows = list(reader)

            self.assertEqual(reader.fieldnames, REPORT_COLUMNS)
            self.assertEqual(len(rows), 5)


if __name__ == "__main__":
    unittest.main()
