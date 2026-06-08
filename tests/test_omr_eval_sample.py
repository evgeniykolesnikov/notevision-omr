"""Tests for the thesis OMR evaluation sample."""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_omr_eval_sample import (
    GROUP_MANUAL,
    GROUP_TEMPLATE,
    PROBLEMATIC_DOC_IDS,
    build_omr_eval_sample,
)


def _row(
    page_index: int,
    *,
    doc_id: str = "doc-a",
    page_type: str = "music",
    has_music: int = 1,
    score: float = 0.99,
    validation_source: str = "template_prediction",
) -> dict[str, str]:
    return {
        "doc_id": doc_id,
        "page_index": str(page_index),
        "page_type": page_type,
        "has_music": str(has_music),
        "quality_comment": "",
        "image_path": f"outputs/pages/{doc_id}/page_{page_index:03d}.png",
        "has_music_pred": "1",
        "has_music_score": str(score),
        "validation_source": validation_source,
        "needs_review": "0",
    }


def _keys(rows: list[dict[str, str]]) -> set[tuple[str, str]]:
    return {(row["doc_id"], row["page_index"]) for row in rows}


class OmrEvalSampleTests(unittest.TestCase):
    def test_non_music_pages_are_excluded(self) -> None:
        rows = [
            _row(1, page_type="music", has_music=0),
            _row(2, page_type="music", has_music=1),
        ]

        sample = build_omr_eval_sample(rows, limit=10)

        self.assertEqual(_keys(sample), {("doc-a", "2")})

    def test_non_eligible_page_types_are_excluded(self) -> None:
        rows = [
            _row(index, page_type=page_type)
            for index, page_type in enumerate(
                ["unknown", "title", "text", "blank"],
                start=1,
            )
        ]

        sample = build_omr_eval_sample(rows, limit=10)

        self.assertEqual(sample, [])

    def test_music_and_mixed_pages_are_included_and_grouped(self) -> None:
        rows = [
            _row(1, page_type="music", validation_source="manual_thesis"),
            _row(2, page_type="mixed"),
        ]

        sample = build_omr_eval_sample(rows, limit=10)

        self.assertEqual(len(sample), 2)
        by_page = {row["page_index"]: row for row in sample}
        self.assertEqual(by_page["1"]["omr_eval_group"], GROUP_MANUAL)
        self.assertEqual(by_page["2"]["omr_eval_group"], GROUP_TEMPLATE)

    def test_problematic_document_is_prioritized(self) -> None:
        problematic_doc = sorted(PROBLEMATIC_DOC_IDS)[0]
        rows = [
            _row(1, doc_id="ordinary-doc"),
            _row(1, doc_id=problematic_doc),
        ]

        sample = build_omr_eval_sample(rows, limit=1, random_seed=7)

        self.assertEqual(sample[0]["doc_id"], problematic_doc)

    def test_limit_is_respected_and_duplicates_are_removed(self) -> None:
        rows = [_row(index) for index in range(1, 11)]
        rows.append(_row(1))

        sample = build_omr_eval_sample(rows, limit=4, random_seed=5)

        self.assertEqual(len(sample), 4)
        self.assertEqual(len(_keys(sample)), 4)

    def test_random_seed_is_reproducible(self) -> None:
        rows = [_row(index) for index in range(1, 21)]

        first = build_omr_eval_sample(rows, limit=5, random_seed=42)
        second = build_omr_eval_sample(rows, limit=5, random_seed=42)

        self.assertEqual(_keys(first), _keys(second))


if __name__ == "__main__":
    unittest.main()
