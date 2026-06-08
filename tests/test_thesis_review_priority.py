"""Tests for building the compact thesis review priority sample."""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_thesis_review_priority import (
    GROUP_BOUNDARY,
    GROUP_RANDOM_MUSIC,
    GROUP_UNCERTAIN,
    GROUP_UNKNOWN,
    build_thesis_review_priority,
)


def _row(
    page_index: int,
    *,
    reason: str,
    prediction: int = 0,
    score: float = 0.0,
    doc_id: str = "doc-a",
) -> dict[str, str]:
    return {
        "doc_id": doc_id,
        "page_index": str(page_index),
        "page_type": "music" if prediction else "unknown",
        "has_music": str(prediction),
        "quality_comment": "",
        "image_path": f"{doc_id}/page_{page_index:03d}.png",
        "has_music_pred": str(prediction),
        "has_music_score": str(score),
        "validation_source": "template_prediction",
        "needs_review": "1",
        "review_reason": reason,
    }


def _by_key(
    rows: list[dict[str, str]],
) -> dict[tuple[str, str], dict[str, str]]:
    return {(row["doc_id"], row["page_index"]): row for row in rows}


class ThesisReviewPriorityTests(unittest.TestCase):
    def test_template_prediction_only_is_excluded(self) -> None:
        rows = [_row(1, reason="template_prediction")]

        priority = build_thesis_review_priority(
            rows,
            random_confident_music=0,
        )

        self.assertEqual(priority, [])

    def test_unknown_is_included(self) -> None:
        rows = [_row(1, reason="template_prediction;unknown")]

        priority = build_thesis_review_priority(
            rows,
            random_confident_music=0,
        )

        self.assertEqual(priority[0]["priority_group"], GROUP_UNKNOWN)

    def test_uncertain_score_is_included(self) -> None:
        rows = [_row(1, reason="uncertain_score", score=0.5)]

        priority = build_thesis_review_priority(
            rows,
            random_confident_music=0,
        )

        self.assertEqual(priority[0]["priority_group"], GROUP_UNCERTAIN)

    def test_first_and_last_pages_are_included(self) -> None:
        rows = [
            _row(1, reason="first_2_pages"),
            _row(10, reason="last_2_pages"),
        ]

        priority = build_thesis_review_priority(
            rows,
            random_confident_music=0,
        )

        groups = {
            row["page_index"]: row["priority_group"] for row in priority
        }
        self.assertEqual(groups["1"], GROUP_BOUNDARY)
        self.assertEqual(groups["10"], GROUP_BOUNDARY)

    def test_random_confident_music_is_reproducible(self) -> None:
        rows = [
            _row(
                page_index,
                reason="template_prediction",
                prediction=1,
                score=0.99,
            )
            for page_index in range(1, 11)
        ]

        first = build_thesis_review_priority(
            rows,
            random_confident_music=3,
            random_seed=7,
        )
        second = build_thesis_review_priority(
            rows,
            random_confident_music=3,
            random_seed=7,
        )

        first_keys = [(row["doc_id"], row["page_index"]) for row in first]
        second_keys = [(row["doc_id"], row["page_index"]) for row in second]
        self.assertEqual(first_keys, second_keys)
        self.assertEqual(len(first_keys), 3)
        self.assertTrue(
            all(
                row["priority_group"] == GROUP_RANDOM_MUSIC
                for row in first
            )
        )

    def test_priority_group_combines_applicable_groups(self) -> None:
        rows = [
            _row(
                1,
                reason=(
                    "unknown;uncertain_score;first_2_pages;"
                    "random_confident_music"
                ),
                prediction=1,
                score=0.99,
            )
        ]

        priority = build_thesis_review_priority(
            rows,
            random_confident_music=1,
            random_seed=42,
        )
        groups = priority[0]["priority_group"].split(";")

        self.assertEqual(
            groups,
            [
                GROUP_BOUNDARY,
                GROUP_UNCERTAIN,
                GROUP_UNKNOWN,
                GROUP_RANDOM_MUSIC,
            ],
        )


if __name__ == "__main__":
    unittest.main()
