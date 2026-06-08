"""Tests for initializing MusicXML expert-review artifacts."""

import csv
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from init_omr_expert_review import (
    EXPERT_COLUMNS,
    FAILURE_COLUMNS,
    build_expert_review_rows,
    build_failure_review_rows,
    initialize_omr_expert_review,
)


def _make_mxl(root: Path, doc_id: str, page_index: int) -> Path:
    path = root / doc_id / f"page_{page_index:03d}" / f"page_{page_index:03d}.mxl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"mxl")
    return path


class InitOmrExpertReviewTests(unittest.TestCase):
    def test_expert_rows_have_all_planned_columns_and_empty_review_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            mxl = _make_mxl(Path(temporary_dir), "doc-a", 1)
            rows = [
                {
                    "doc_id": "doc-a",
                    "page_index": "1",
                    "page_type": "music",
                    "image_path": "page.png",
                    "has_music_score": "0.99",
                    "selection_reason": "random_successful",
                    "mxl_path": str(mxl),
                }
            ]

            expert = build_expert_review_rows(rows)

            self.assertEqual(list(expert[0]), EXPERT_COLUMNS)
            self.assertEqual(expert[0]["pitch_errors"], "")
            self.assertEqual(expert[0]["page_usable"], "")

    def test_failure_rows_are_derived_from_missing_mxl_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            omr_dir = Path(temporary_dir) / "omr"
            _make_mxl(omr_dir, "doc-a", 1)
            rows = [
                {
                    "doc_id": "doc-a",
                    "page_index": "1",
                    "page_type": "music",
                    "image_path": "one.png",
                },
                {
                    "doc_id": "doc-b",
                    "page_index": "2",
                    "page_type": "mixed",
                    "image_path": "two.png",
                },
            ]

            failures = build_failure_review_rows(rows, omr_dir)

            self.assertEqual(len(failures), 1)
            self.assertEqual(failures[0]["doc_id"], "doc-b")
            self.assertEqual(list(failures[0]), FAILURE_COLUMNS)

    def test_initializer_writes_both_csvs_and_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            omr_dir = root / "omr"
            mxl = _make_mxl(omr_dir, "doc-a", 1)
            ground_truth = root / "ground_truth.csv"
            omr_sample = root / "omr_sample.csv"
            expert_out = root / "expert.csv"
            failure_out = root / "failures.csv"
            protocol_out = root / "protocol.md"

            with ground_truth.open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=[
                        "doc_id",
                        "page_index",
                        "page_type",
                        "image_path",
                        "has_music_score",
                        "selection_reason",
                        "mxl_path",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "doc_id": "doc-a",
                        "page_index": 1,
                        "page_type": "music",
                        "image_path": "one.png",
                        "has_music_score": 0.99,
                        "selection_reason": "random_successful",
                        "mxl_path": str(mxl),
                    }
                )

            with omr_sample.open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=[
                        "doc_id",
                        "page_index",
                        "page_type",
                        "image_path",
                        "has_music_score",
                    ],
                )
                writer.writeheader()
                writer.writerows(
                    [
                        {
                            "doc_id": "doc-a",
                            "page_index": 1,
                            "page_type": "music",
                            "image_path": "one.png",
                            "has_music_score": 0.99,
                        },
                        {
                            "doc_id": "doc-b",
                            "page_index": 2,
                            "page_type": "mixed",
                            "image_path": "two.png",
                            "has_music_score": 0.5,
                        },
                    ]
                )

            summary = initialize_omr_expert_review(
                ground_truth,
                omr_sample,
                omr_dir,
                expert_out,
                failure_out,
                protocol_out,
            )

            self.assertEqual(summary, {"expert_pages": 1, "failure_pages": 1})
            self.assertTrue(expert_out.is_file())
            self.assertTrue(failure_out.is_file())
            self.assertIn(
                "Технический результат `141/150 = 94%`",
                protocol_out.read_text(encoding="utf-8"),
            )

    def test_missing_mxl_in_selected_sample_is_rejected(self) -> None:
        rows = [
            {
                "doc_id": "doc-a",
                "page_index": "1",
                "page_type": "music",
                "image_path": "page.png",
                "has_music_score": "0.9",
                "selection_reason": "low_confidence",
                "mxl_path": "missing.mxl",
            }
        ]

        with self.assertRaisesRegex(FileNotFoundError, "MXL file"):
            build_expert_review_rows(rows)


if __name__ == "__main__":
    unittest.main()
