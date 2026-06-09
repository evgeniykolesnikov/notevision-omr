"""Tests for the expanded thesis OMR evaluation sample."""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_omr_eval_sample import (  # noqa: E402
    OUTPUT_COLUMNS,
    build_omr_eval_sample,
    write_sample_csv,
    write_summary,
)


def _label(
    doc_id: str,
    page_index: int,
    *,
    page_type: str = "music",
    has_music: int = 1,
) -> dict[str, str]:
    return {
        "doc_id": doc_id,
        "page_index": str(page_index),
        "page_type": page_type,
        "has_music": str(has_music),
        "image_path": f"outputs/pages/{doc_id}/page_{page_index:03d}.png",
    }


def _prediction(
    doc_id: str,
    page_index: int,
    prediction: int,
    score: float = 0.99,
) -> dict[str, str]:
    return {
        "doc_id": doc_id,
        "page_index": str(page_index),
        "prediction": str(prediction),
        "score": str(score),
        "status": "success",
    }


def _make_page(pages_dir: Path, doc_id: str, page_index: int) -> None:
    path = pages_dir / doc_id / f"page_{page_index:03d}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"PNG")


class OmrEvalSampleTests(unittest.TestCase):
    def test_only_existing_likely_music_pages_are_sampled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pages_dir = Path(temp_dir) / "pages"
            _make_page(pages_dir, "doc-a", 1)
            _make_page(pages_dir, "doc-a", 2)
            labels = [
                _label("doc-a", 1, page_type="music"),
                _label("doc-a", 2, page_type="text", has_music=0),
                _label("doc-a", 3, page_type="music"),
            ]

            sample, summary = build_omr_eval_sample(
                labels,
                pages_dir=pages_dir,
                sample_size=10,
            )

            self.assertEqual(
                {(row["doc_id"], row["page_index"]) for row in sample},
                {("doc-a", 1)},
            )
            self.assertEqual(summary["sampled_pages"], 1)
            self.assertTrue(summary["warning"])

    def test_predictions_can_add_candidate_without_manual_music_label(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pages_dir = Path(temp_dir) / "pages"
            _make_page(pages_dir, "doc-a", 1)

            sample, _ = build_omr_eval_sample(
                [_label("doc-a", 1, page_type="unknown", has_music=0)],
                pages_dir=pages_dir,
                cnn_rows=[_prediction("doc-a", 1, 1)],
                sample_size=1,
            )

            self.assertEqual(len(sample), 1)
            self.assertEqual(sample[0]["cnn_prediction"], 1)

    def test_failures_disagreements_and_mixed_pages_are_prioritized(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pages_dir = Path(temp_dir) / "pages"
            labels = []
            for page_index in range(1, 7):
                _make_page(pages_dir, "doc-a", page_index)
                labels.append(
                    _label(
                        "doc-a",
                        page_index,
                        page_type="mixed" if page_index == 3 else "music",
                    )
                )
            cnn = [_prediction("doc-a", index, 1) for index in range(1, 7)]
            classical = [
                _prediction("doc-a", index, 0 if index == 2 else 1)
                for index in range(1, 7)
            ]
            failures = [
                {
                    "doc_id": "doc-a",
                    "page_index": "1",
                    "failure_type": "missing_mxl",
                }
            ]

            sample, _ = build_omr_eval_sample(
                labels,
                pages_dir=pages_dir,
                cnn_rows=cnn,
                classical_rows=classical,
                failure_rows=failures,
                sample_size=3,
            )

            by_page = {row["page_index"]: row for row in sample}
            self.assertEqual(set(by_page), {1, 2, 3})
            self.assertEqual(
                by_page[1]["sample_group"], "previous_omr_failure"
            )
            self.assertEqual(by_page[2]["sample_group"], "model_disagreement")
            self.assertEqual(by_page[3]["sample_group"], "mixed_page")

    def test_fallback_recovery_and_low_confidence_are_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pages_dir = Path(temp_dir) / "pages"
            for page_index in (1, 2):
                _make_page(pages_dir, "doc-a", page_index)
            fallback = [
                {
                    "doc_id": "doc-a",
                    "page_index": "1",
                    "preprocessing_fallback_status": "recovered",
                    "preprocessing_mxl_path": "result.mxl",
                }
            ]

            sample, _ = build_omr_eval_sample(
                [_label("doc-a", 1), _label("doc-a", 2)],
                pages_dir=pages_dir,
                cnn_rows=[
                    _prediction("doc-a", 1, 1),
                    _prediction("doc-a", 2, 1, score=0.7),
                ],
                fallback_rows=fallback,
                sample_size=2,
            )

            by_page = {row["page_index"]: row for row in sample}
            self.assertEqual(by_page[1]["sample_group"], "fallback_recovered")
            self.assertEqual(
                by_page[2]["sample_group"], "low_confidence_candidate"
            )

    def test_exact_size_deduplication_multiple_documents_and_seed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pages_dir = Path(temp_dir) / "pages"
            labels = []
            for doc_index in range(8):
                doc_id = f"doc-{doc_index}"
                for page_index in range(1, 41):
                    _make_page(pages_dir, doc_id, page_index)
                    labels.append(_label(doc_id, page_index))
            labels.append(dict(labels[0]))

            first, _ = build_omr_eval_sample(
                labels,
                pages_dir=pages_dir,
                sample_size=300,
                random_seed=42,
            )
            second, _ = build_omr_eval_sample(
                labels,
                pages_dir=pages_dir,
                sample_size=300,
                random_seed=42,
            )

            first_keys = [
                (row["doc_id"], row["page_index"]) for row in first
            ]
            self.assertEqual(len(first), 300)
            self.assertEqual(len(set(first_keys)), 300)
            self.assertGreater(len({row["doc_id"] for row in first}), 1)
            self.assertEqual(first, second)

    def test_csv_and_summary_are_created(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pages_dir = root / "pages"
            _make_page(pages_dir, "doc-a", 1)
            rows, summary = build_omr_eval_sample(
                [_label("doc-a", 1)],
                pages_dir=pages_dir,
                sample_size=1,
                random_seed=7,
            )
            output = root / "sample.csv"
            summary_path = root / "summary.md"

            write_sample_csv(rows, output)
            write_summary(summary, summary_path)

            with output.open(encoding="utf-8", newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                saved = list(reader)
            self.assertEqual(reader.fieldnames, OUTPUT_COLUMNS)
            self.assertEqual(len(saved), 1)
            text = summary_path.read_text(encoding="utf-8")
            self.assertIn("Total sampled pages: 1", text)
            self.assertIn("Random seed: 7", text)
            self.assertIn("All image paths exist: True", text)


if __name__ == "__main__":
    unittest.main()
