"""Tests for legacy and thesis OMR candidate compatibility."""

import sys
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from notevision.omr.candidate_adapter import (
    NORMALIZED_EXISTS,
    NORMALIZED_INPUT_KIND,
    NORMALIZED_INPUT_PATH,
    NORMALIZED_SELECTED,
    adapt_omr_candidates,
)


class OmrCandidateAdapterTests(unittest.TestCase):
    def test_legacy_format_preserves_preprocessed_path_and_exists(self) -> None:
        candidates = pd.DataFrame(
            {
                "doc_id": ["doc-a", "doc-b"],
                "page_index": [1, 2],
                "preprocessed_path": ["prepared/a.png", "prepared/b.png"],
                "exists": [True, False],
            }
        )

        normalized = adapt_omr_candidates(candidates)

        self.assertEqual(
            normalized[NORMALIZED_INPUT_PATH].tolist(),
            ["prepared/a.png", "prepared/b.png"],
        )
        self.assertEqual(
            normalized[NORMALIZED_EXISTS].tolist(),
            [True, False],
        )
        self.assertTrue(normalized[NORMALIZED_SELECTED].all())

    def test_thesis_format_uses_image_path_and_music_filter(self) -> None:
        candidates = pd.DataFrame(
            {
                "doc_id": ["doc-a", "doc-a", "doc-a"],
                "page_index": [1, 2, 3],
                "image_path": ["one.png", "two.png", "three.png"],
                "has_music": [1, 1, 0],
                "page_type": ["music", "mixed", "text"],
            }
        )

        normalized = adapt_omr_candidates(candidates)

        self.assertEqual(
            normalized[NORMALIZED_INPUT_PATH].tolist(),
            ["one.png", "two.png", "three.png"],
        )
        self.assertEqual(
            normalized[NORMALIZED_INPUT_KIND].tolist(),
            ["image_path", "image_path", "image_path"],
        )
        self.assertEqual(
            normalized[NORMALIZED_SELECTED].tolist(),
            [True, True, False],
        )

    def test_mixed_format_uses_row_level_fallback(self) -> None:
        candidates = pd.DataFrame(
            {
                "doc_id": ["doc-a", "doc-b"],
                "page_index": [1, 2],
                "preprocessed_path": ["prepared/a.png", ""],
                "exists": [True, False],
                "image_path": ["pages/a.png", "pages/b.png"],
                "has_music": [1, 1],
                "page_type": ["music", "music"],
            }
        )

        normalized = adapt_omr_candidates(candidates)

        self.assertEqual(
            normalized[NORMALIZED_INPUT_PATH].tolist(),
            ["prepared/a.png", "pages/b.png"],
        )
        self.assertEqual(
            normalized[NORMALIZED_INPUT_KIND].tolist(),
            ["preprocessed", "image_path"],
        )
        self.assertEqual(
            normalized[NORMALIZED_EXISTS].tolist(),
            [True, True],
        )


if __name__ == "__main__":
    unittest.main()
