"""Tests for manual OMR failure review summary generation."""

import csv
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from analyze_failure_review import analyze_failure_review, analyze_file


class AnalyzeFailureReviewTests(unittest.TestCase):
    def test_analyze_counts_distributions_and_derived_metrics(self) -> None:
        rows = [
            {
                "corrected_page_type": "music",
                "decision": "requires_manual_review",
                "failure_reason": "low_contrast",
                "classifier_error_type": "none",
                "review_status": "reviewed",
            },
            {
                "corrected_page_type": "title",
                "decision": "exclude_from_omr",
                "failure_reason": "title_page",
                "classifier_error_type": "false_positive_music",
                "review_status": "reviewed",
            },
            {
                "corrected_page_type": "blank",
                "decision": "exclude_from_omr",
                "failure_reason": "blank_page",
                "classifier_error_type": "false_positive_music",
                "review_status": "draft",
            },
            {
                "corrected_page_type": "mixed",
                "decision": "retry_400dpi",
                "failure_reason": "small_interline",
                "classifier_error_type": "none",
                "review_status": "reviewed",
            },
        ]
        metrics = analyze_failure_review(
            rows,
            [
                "corrected_page_type",
                "decision",
                "failure_reason",
                "classifier_error_type",
                "review_status",
            ],
        )

        self.assertEqual(metrics["total_rows"], 4)
        self.assertEqual(metrics["reviewed_rows"], 3)
        self.assertEqual(
            metrics["distributions"]["corrected_page_type"]["music"],
            1,
        )
        self.assertEqual(metrics["distributions"]["decision"]["exclude_from_omr"], 2)
        self.assertEqual(metrics["derived_counts"]["real_omr_cases"], 2)
        self.assertEqual(metrics["derived_counts"]["routing_errors"], 2)
        self.assertEqual(metrics["derived_counts"]["hard_negatives"], 2)
        self.assertEqual(metrics["derived_percents"]["routing_errors"], 50.0)

    def test_analyze_file_creates_markdown_and_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            input_path = root / "failure_review.csv"
            summary_md = root / "summary.md"
            summary_csv = root / "summary.csv"
            with input_path.open("w", encoding="utf-8", newline="") as csv_file:
                writer = csv.DictWriter(
                    csv_file,
                    fieldnames=(
                        "corrected_page_type",
                        "decision",
                        "failure_reason",
                        "classifier_error_type",
                        "review_status",
                    ),
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "corrected_page_type": "cover",
                        "decision": "exclude_from_omr",
                        "failure_reason": "cover_page",
                        "classifier_error_type": "false_positive_music",
                        "review_status": "reviewed",
                    }
                )

            metrics = analyze_file(input_path, summary_md, summary_csv)

            self.assertEqual(metrics["total_rows"], 1)
            self.assertTrue(summary_md.is_file())
            self.assertTrue(summary_csv.is_file())
            self.assertIn("Failure Review Summary", summary_md.read_text(encoding="utf-8"))
            rows = list(
                csv.DictReader(summary_csv.open(encoding="utf-8", newline=""))
            )
            self.assertIn(
                {
                    "section": "derived",
                    "name": "hard_negatives",
                    "count": "1",
                    "percent": "100.0",
                },
                rows,
            )

    def test_missing_optional_columns_do_not_crash(self) -> None:
        rows = [{"corrected_page_type": "music"}, {"corrected_page_type": "title"}]
        metrics = analyze_failure_review(rows, ["corrected_page_type"])

        self.assertEqual(metrics["total_rows"], 2)
        self.assertEqual(metrics["reviewed_rows"], 0)
        self.assertEqual(metrics["derived_counts"]["real_omr_cases"], 1)
        self.assertEqual(metrics["derived_counts"]["routing_errors"], 0)
        self.assertEqual(metrics["derived_counts"]["hard_negatives"], 1)
        self.assertEqual(metrics["distributions"]["decision"], {})


if __name__ == "__main__":
    unittest.main()
