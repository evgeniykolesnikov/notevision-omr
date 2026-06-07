"""Tests for building the OMR candidate list."""

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_omr_candidates import build_omr_candidates


def _labels() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "doc_id": ["doc-a", "doc-a", "doc-b", "doc-b"],
            "page_index": [1, 2, 1, 2],
            "page_type": ["music", "text", "music", "music"],
            "has_music": [1, 1, 0, 1],
            "image_path": ["a1.png", "a2.png", "b1.png", "b2.png"],
            "quality_comment": ["", "text page", "", "faint scan"],
        }
    )


class OmrCandidateTests(unittest.TestCase):
    def test_only_validated_music_pages_are_selected(self) -> None:
        candidates = build_omr_candidates(_labels())

        self.assertEqual(
            list(zip(candidates["doc_id"], candidates["page_index"])),
            [("doc-a", 1), ("doc-b", 2)],
        )
        self.assertTrue((candidates["has_music"] == 1).all())
        self.assertTrue((candidates["page_type"] == "music").all())

    def test_preprocessed_path_and_exists_are_built_correctly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            expected = (
                root
                / "outputs"
                / "preprocessed"
                / "doc-a"
                / "page_001_binary.png"
            )
            expected.parent.mkdir(parents=True)
            expected.touch()

            candidates = build_omr_candidates(
                _labels(),
                doc_id="doc-a",
                project_root=root,
            )

            self.assertEqual(
                candidates.iloc[0]["preprocessed_path"],
                str(
                    Path("outputs")
                    / "preprocessed"
                    / "doc-a"
                    / "page_001_binary.png"
                ),
            )
            self.assertTrue(bool(candidates.iloc[0]["exists"]))

    def test_limit_restricts_candidate_count(self) -> None:
        candidates = build_omr_candidates(_labels(), limit=1)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates.iloc[0]["doc_id"], "doc-a")
        self.assertEqual(candidates.iloc[0]["page_index"], 1)


if __name__ == "__main__":
    unittest.main()
