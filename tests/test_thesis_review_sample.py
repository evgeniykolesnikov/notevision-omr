"""Tests for building the thesis page-review sample."""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_thesis_review_sample import (
    REASON_FIRST,
    REASON_LAST,
    REASON_RANDOM_MUSIC,
    REASON_UNCERTAIN,
    REASON_UNKNOWN,
    build_thesis_review_sample,
)


def _row(
    page_index: int,
    *,
    doc_id: str = "doc-a",
    page_type: str = "music",
    prediction: int = 1,
    score: float = 0.99,
    validation_source: str = "manual_previous",
) -> dict[str, str]:
    return {
        "doc_id": doc_id,
        "page_index": str(page_index),
        "page_type": page_type,
        "has_music": str(prediction),
        "quality_comment": "",
        "image_path": f"{doc_id}/page_{page_index:03d}.png",
        "has_music_pred": str(prediction),
        "has_music_score": str(score),
        "validation_source": validation_source,
        "needs_review": "0",
    }


def _by_key(
    rows: list[dict[str, str]],
) -> dict[tuple[str, str], dict[str, str]]:
    return {(row["doc_id"], row["page_index"]): row for row in rows}


class ThesisReviewSampleTests(unittest.TestCase):
    def test_unknown_page_is_selected(self) -> None:
        rows = [_row(1), _row(2), _row(3, page_type="unknown")]

        sample = build_thesis_review_sample(rows, random_music=0)

        selected = _by_key(sample)[("doc-a", "3")]
        self.assertIn(REASON_UNKNOWN, selected["review_reason"])

    def test_uncertain_score_is_selected(self) -> None:
        rows = [_row(1), _row(2), _row(3, score=0.5)]

        sample = build_thesis_review_sample(rows, random_music=0)

        selected = _by_key(sample)[("doc-a", "3")]
        self.assertIn(REASON_UNCERTAIN, selected["review_reason"])

    def test_first_and_last_two_pages_are_selected(self) -> None:
        rows = [_row(page_index) for page_index in range(1, 7)]

        sample = build_thesis_review_sample(rows, random_music=0)
        selected = _by_key(sample)

        self.assertIn(REASON_FIRST, selected[("doc-a", "1")]["review_reason"])
        self.assertIn(REASON_FIRST, selected[("doc-a", "2")]["review_reason"])
        self.assertIn(REASON_LAST, selected[("doc-a", "5")]["review_reason"])
        self.assertIn(REASON_LAST, selected[("doc-a", "6")]["review_reason"])
        self.assertNotIn(("doc-a", "3"), selected)

    def test_random_confident_music_is_reproducible(self) -> None:
        rows = [_row(page_index) for page_index in range(1, 11)]

        first = build_thesis_review_sample(
            rows,
            random_music=3,
            random_seed=7,
        )
        second = build_thesis_review_sample(
            rows,
            random_music=3,
            random_seed=7,
        )

        first_random = {
            (row["doc_id"], row["page_index"])
            for row in first
            if REASON_RANDOM_MUSIC in row["review_reason"].split(";")
        }
        second_random = {
            (row["doc_id"], row["page_index"])
            for row in second
            if REASON_RANDOM_MUSIC in row["review_reason"].split(";")
        }
        self.assertEqual(first_random, second_random)
        self.assertEqual(len(first_random), 3)

    def test_duplicate_page_keys_are_removed(self) -> None:
        rows = [_row(1), _row(1), _row(2), _row(3)]

        sample = build_thesis_review_sample(rows, random_music=0)
        keys = [(row["doc_id"], row["page_index"]) for row in sample]

        self.assertEqual(len(keys), len(set(keys)))

    def test_review_reason_combines_multiple_reasons(self) -> None:
        rows = [
            _row(
                1,
                page_type="unknown",
                prediction=0,
                score=0.5,
                validation_source="template_prediction",
            ),
            _row(2),
            _row(3),
        ]

        sample = build_thesis_review_sample(rows, random_music=0)
        reasons = _by_key(sample)[("doc-a", "1")]["review_reason"]

        self.assertIn(";", reasons)
        self.assertIn("template_prediction", reasons)
        self.assertIn(REASON_UNKNOWN, reasons)
        self.assertIn(REASON_UNCERTAIN, reasons)
        self.assertIn(REASON_FIRST, reasons)


if __name__ == "__main__":
    unittest.main()
