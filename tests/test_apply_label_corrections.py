"""Tests for applying exported thesis label corrections."""

import csv
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from apply_label_corrections import apply_label_corrections

LABEL_COLUMNS = [
    "doc_id",
    "page_index",
    "page_type",
    "has_music",
    "quality_comment",
    "image_path",
    "has_music_pred",
    "has_music_score",
    "validation_source",
    "needs_review",
]
CORRECTION_COLUMNS = [
    "doc_id",
    "page_index",
    "page_type",
    "has_music",
    "quality_comment",
]


def _write_csv(
    path: Path,
    columns: list[str],
    rows: list[dict[str, str]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _label_row() -> dict[str, str]:
    return {
        "doc_id": "doc-a",
        "page_index": "1",
        "page_type": "unknown",
        "has_music": "0",
        "quality_comment": "",
        "image_path": "page_001.png",
        "has_music_pred": "1",
        "has_music_score": "0.8",
        "validation_source": "template_prediction",
        "needs_review": "1",
    }


class ApplyLabelCorrectionsTests(unittest.TestCase):
    def _paths(self, root: Path) -> tuple[Path, Path, Path]:
        return (
            root / "labels.csv",
            root / "corrections.csv",
            root / "output.csv",
        )

    def test_apply_updates_page_type_has_music_and_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            labels, corrections, output = self._paths(root)
            _write_csv(labels, LABEL_COLUMNS, [_label_row()])
            _write_csv(
                corrections,
                CORRECTION_COLUMNS,
                [
                    {
                        "doc_id": "doc-a",
                        "page_index": "1",
                        "page_type": "music",
                        "has_music": "1",
                        "quality_comment": "verified",
                    }
                ],
            )

            summary = apply_label_corrections(labels, corrections, output)
            with output.open(encoding="utf-8", newline="") as csv_file:
                row = next(csv.DictReader(csv_file))

            self.assertEqual(summary["applied"], 1)
            self.assertEqual(row["page_type"], "music")
            self.assertEqual(row["has_music"], "1")
            self.assertEqual(row["quality_comment"], "verified")
            self.assertEqual(row["validation_source"], "manual_thesis")
            self.assertEqual(row["needs_review"], "0")

    def test_unknown_correction_adds_warning_without_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            labels, corrections, output = self._paths(root)
            _write_csv(labels, LABEL_COLUMNS, [_label_row()])
            _write_csv(
                corrections,
                CORRECTION_COLUMNS,
                [
                    {
                        "doc_id": "missing-doc",
                        "page_index": "9",
                        "page_type": "blank",
                        "has_music": "0",
                        "quality_comment": "",
                    }
                ],
            )

            summary = apply_label_corrections(labels, corrections, output)

            self.assertEqual(summary["applied"], 0)
            self.assertEqual(len(summary["warnings"]), 1)
            self.assertTrue(output.is_file())

    def test_empty_corrections_do_not_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            labels, corrections, _ = self._paths(root)
            _write_csv(labels, LABEL_COLUMNS, [_label_row()])
            _write_csv(corrections, CORRECTION_COLUMNS, [])

            summary = apply_label_corrections(labels, corrections, labels)
            with labels.open(encoding="utf-8", newline="") as csv_file:
                rows = list(csv.DictReader(csv_file))

            self.assertEqual(summary["corrections_rows"], 0)
            self.assertEqual(summary["applied"], 0)
            self.assertEqual(len(rows), 1)

    def test_non_empty_corrections_can_replace_labels_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            labels, corrections, _ = self._paths(root)
            _write_csv(labels, LABEL_COLUMNS, [_label_row()])
            _write_csv(
                corrections,
                CORRECTION_COLUMNS,
                [
                    {
                        "doc_id": "doc-a",
                        "page_index": "1",
                        "page_type": "text",
                        "has_music": "0",
                        "quality_comment": "checked in place",
                    }
                ],
            )

            summary = apply_label_corrections(labels, corrections, labels)
            with labels.open(encoding="utf-8", newline="") as csv_file:
                row = next(csv.DictReader(csv_file))

            self.assertEqual(summary["applied"], 1)
            self.assertEqual(row["page_type"], "text")
            self.assertEqual(row["quality_comment"], "checked in place")
            self.assertEqual(row["validation_source"], "manual_thesis")


if __name__ == "__main__":
    unittest.main()
