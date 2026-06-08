"""Tests for the MusicXML expert-review sample builder."""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_omr_ground_truth_sample import (
    REASON_FAILURE_DOCUMENT,
    REASON_LOW_CONFIDENCE,
    REASON_MIXED,
    build_omr_ground_truth_sample,
)


def _row(
    doc_id: str,
    page_index: int,
    *,
    page_type: str = "music",
    score: float = 0.99,
) -> dict[str, str]:
    return {
        "doc_id": doc_id,
        "page_index": str(page_index),
        "page_type": page_type,
        "image_path": f"pages/{doc_id}/page_{page_index:03d}.png",
        "has_music_score": str(score),
    }


def _make_mxl(root: Path, doc_id: str, page_index: int) -> Path:
    path = root / doc_id / f"page_{page_index:03d}" / f"page_{page_index:03d}.mxl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"mxl")
    return path


class BuildOmrGroundTruthSampleTests(unittest.TestCase):
    def test_selects_only_pages_with_existing_mxl_and_priority_groups(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            omr_dir = Path(temporary_dir) / "omr"
            rows = [
                _row("doc-a", 1, page_type="mixed"),
                _row("doc-a", 2, score=0.4),
                _row("doc-b", 1),
                _row("doc-b", 2),
                _row("doc-c", 1),
                _row("doc-c", 2),
            ]
            for row in rows:
                if not (row["doc_id"] == "doc-b" and row["page_index"] == "2"):
                    _make_mxl(
                        omr_dir,
                        row["doc_id"],
                        int(row["page_index"]),
                    )

            sample = build_omr_ground_truth_sample(
                rows,
                omr_dir,
                limit=4,
                random_seed=3,
                mixed_target=1,
                failure_document_target=1,
                low_confidence_target=1,
            )

            keys = {(row["doc_id"], row["page_index"]) for row in sample}
            self.assertNotIn(("doc-b", "2"), keys)
            reasons = ";".join(row["selection_reason"] for row in sample)
            self.assertIn(REASON_MIXED, reasons)
            self.assertIn(REASON_FAILURE_DOCUMENT, reasons)
            self.assertIn(REASON_LOW_CONFIDENCE, reasons)
            self.assertTrue(all(Path(row["mxl_path"]).is_file() for row in sample))

    def test_random_seed_is_reproducible_and_limit_is_respected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            omr_dir = Path(temporary_dir) / "omr"
            rows = [_row("doc-a", page) for page in range(1, 11)]
            for row in rows:
                _make_mxl(omr_dir, "doc-a", int(row["page_index"]))

            first = build_omr_ground_truth_sample(
                rows,
                omr_dir,
                limit=5,
                random_seed=42,
                mixed_target=0,
                failure_document_target=0,
                low_confidence_target=0,
            )
            second = build_omr_ground_truth_sample(
                rows,
                omr_dir,
                limit=5,
                random_seed=42,
                mixed_target=0,
                failure_document_target=0,
                low_confidence_target=0,
            )

            self.assertEqual(
                [(row["doc_id"], row["page_index"]) for row in first],
                [(row["doc_id"], row["page_index"]) for row in second],
            )
            self.assertEqual(len(first), 5)

    def test_missing_omr_directory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            with self.assertRaisesRegex(FileNotFoundError, "OMR directory"):
                build_omr_ground_truth_sample(
                    [_row("doc-a", 1)],
                    Path(temporary_dir) / "missing",
                    limit=1,
                )


if __name__ == "__main__":
    unittest.main()
