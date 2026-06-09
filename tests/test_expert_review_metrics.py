"""Tests for expert review metrics and report generation."""

import csv
import tempfile
import unittest
from pathlib import Path

from scripts.calculate_expert_review_metrics import (
    PROBLEM_FIELDS,
    analyze_expert_reviews,
    filter_review_rows,
    read_review_export,
    write_expert_review_reports,
)


def review_row(**updates: object) -> dict[str, object]:
    row: dict[str, object] = {
        "doc_id": "rsl001",
        "page_index": "1",
        "reviewer_id": "1",
        "reviewer": "Expert A",
        "review_status": "completed",
        "page_usable": "yes",
        "usability_score": "5",
        "checked_measures": "10",
        "correct_measures": "9",
        "reference_notes": "100",
        "matched_notes": "95",
        "pitch_errors": "2",
        "duration_errors": "3",
        "missing_notes": "4",
        "extra_notes": "1",
    }
    row.update({field: "0" for field in PROBLEM_FIELDS})
    row.update(updates)
    return row


class ExpertReviewMetricsTests(unittest.TestCase):
    def test_metrics_ignore_empty_numeric_fields_and_detect_disagreement(self) -> None:
        first = review_row(pitch_problem="1")
        second = review_row(
            reviewer_id="2",
            reviewer="Expert B",
            page_usable="no",
            usability_score="1",
            checked_measures="",
            correct_measures="",
            reference_notes="",
            matched_notes="",
            pitch_errors="",
            duration_errors="",
            missing_notes="",
            extra_notes="",
        )
        draft = review_row(
            page_index="2",
            review_status="draft",
            page_usable="",
            usability_score="",
        )

        analysis = analyze_expert_reviews([first, second, draft])

        self.assertEqual(analysis["experts_count"], 2)
        self.assertEqual(analysis["reviewed_pages"], 2)
        self.assertEqual(analysis["statuses"]["completed"], 2)
        self.assertEqual(analysis["statuses"]["draft"], 1)
        self.assertEqual(analysis["usable_counts"], {"yes": 1, "partial": 0, "no": 1})
        self.assertEqual(analysis["mean_usability_score"], 3)
        self.assertEqual(analysis["problem_rates"]["pitch_problem"]["rate"], 0.5)
        self.assertAlmostEqual(
            analysis["quantitative"]["measure_accuracy"]["value"],
            0.9,
        )
        self.assertEqual(
            analysis["quantitative"]["measure_accuracy"]["denominator"],
            10,
        )
        disagreement = analysis["disagreements"][0]
        self.assertTrue(disagreement["page_usable_disagreement"])
        self.assertEqual(disagreement["usability_score_range"], 4)

    def test_reports_contain_formulas_and_separate_technical_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "reviews.csv"
            metrics_path = root / "metrics.csv"
            summary_path = root / "summary.md"
            rows = [
                review_row(),
                review_row(
                    reviewer_id="2",
                    reviewer="Expert B",
                    usability_score="3",
                    page_usable="partial",
                ),
            ]
            with input_path.open("w", encoding="utf-8", newline="") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)

            write_expert_review_reports(input_path, metrics_path, summary_path)

            with metrics_path.open(encoding="utf-8", newline="") as csv_file:
                metrics = list(csv.DictReader(csv_file))
            self.assertTrue(
                any(row["metric"] == "note_event_error_rate" for row in metrics)
            )
            summary = summary_path.read_text(encoding="utf-8")
            self.assertIn("141/150 (94%)", summary)
            self.assertIn("не входит", summary)
            self.assertIn("Σ correct_measures / Σ checked_measures", summary)
            self.assertIn("`rsl001`", summary)

    def test_reader_rejects_missing_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "invalid.csv"
            path.write_text("doc_id,page_index\nrsl001,1\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "missing required columns"):
                read_review_export(path)

    def test_filters_and_reviewer_averages_are_reported(self) -> None:
        rows = [
            review_row(reviewer="Expert A", usability_score="5"),
            review_row(
                reviewer_id="2",
                reviewer="Expert B",
                usability_score="3",
            ),
            review_row(
                reviewer_id="2",
                reviewer="Expert B",
                page_index="2",
                review_status="draft",
                usability_score="",
            ),
        ]
        filtered, excluded = filter_review_rows(
            rows,
            completed_only=True,
            exclude_reviewers=[" expert a "],
        )
        analysis = analyze_expert_reviews(filtered)

        self.assertEqual(excluded, ["Expert A"])
        self.assertEqual(len(filtered), 1)
        self.assertEqual(analysis["reviewer_mean_scores"], {"Expert B": 3.0})

    def test_report_excludes_igor_and_lists_reviewers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "reviews.csv"
            metrics_path = root / "metrics.csv"
            summary_path = root / "summary.md"
            rows = [
                review_row(reviewer="Valid Expert"),
                review_row(
                    reviewer_id="2",
                    reviewer="Igor",
                    page_index="2",
                    usability_score="1",
                ),
            ]
            with input_path.open("w", encoding="utf-8", newline="") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)

            analysis = write_expert_review_reports(
                input_path,
                metrics_path,
                summary_path,
                completed_only=True,
                exclude_reviewers=["Igor", "Absent Test Reviewer"],
            )

            self.assertEqual(analysis["experts_count"], 1)
            summary = summary_path.read_text(encoding="utf-8")
            self.assertIn("Включённые эксперты: Valid Expert", summary)
            self.assertIn(
                "Исключённые эксперты: Absent Test Reviewer, Igor",
                summary,
            )


if __name__ == "__main__":
    unittest.main()
