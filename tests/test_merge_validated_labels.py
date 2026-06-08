"""Tests for merging previous manual page labels."""

import csv
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from merge_validated_labels import (
    ADDED_COLUMNS,
    REQUIRED_TEMPLATE_COLUMNS,
    merge_validated_labels,
    merge_validated_rows,
)


def _template_rows() -> list[dict[str, str]]:
    return [
        {
            "doc_id": "doc-old",
            "page_index": "1",
            "page_type": "music",
            "has_music": "1",
            "quality_comment": "",
            "image_path": "new/page_001.png",
            "has_music_pred": "1",
            "has_music_score": "0.95",
        },
        {
            "doc_id": "doc-new",
            "page_index": "1",
            "page_type": "music",
            "has_music": "1",
            "quality_comment": "",
            "image_path": "new-doc/page_001.png",
            "has_music_pred": "1",
            "has_music_score": "0.99",
        },
        {
            "doc_id": "doc-new",
            "page_index": "2",
            "page_type": "unknown",
            "has_music": "0",
            "quality_comment": "",
            "image_path": "new-doc/page_002.png",
            "has_music_pred": "0",
            "has_music_score": "0.05",
        },
        {
            "doc_id": "doc-old",
            "page_index": "2",
            "page_type": "music",
            "has_music": "1",
            "quality_comment": "",
            "image_path": "new/page_002.png",
            "has_music_pred": "1",
            "has_music_score": "0.5",
        },
        {
            "doc_id": "doc-old",
            "page_index": "3",
            "page_type": "music",
            "has_music": "1",
            "quality_comment": "",
            "image_path": "new/page_003.png",
            "has_music_pred": "1",
            "has_music_score": "0.95",
        },
    ]


def _validated_rows() -> list[dict[str, str]]:
    return [
        {
            "doc_id": "doc-old",
            "page_index": "1",
            "page_type": "blank",
            "has_music": "0",
            "quality_comment": "checked manually",
            "image_path": "old/page_001.png",
            "has_music_pred": "0",
            "has_music_score": "0.01",
        },
        {
            "doc_id": "doc-old",
            "page_index": "2",
            "page_type": "music",
            "has_music": "1",
            "quality_comment": "confirmed",
            "image_path": "old/page_002.png",
            "has_music_pred": "0",
            "has_music_score": "0.2",
        },
        {
            "doc_id": "doc-old",
            "page_index": "3",
            "page_type": "music",
            "has_music": "1",
            "quality_comment": "confirmed",
            "image_path": "old/page_003.png",
            "has_music_pred": "1",
            "has_music_score": "0.95",
        },
    ]


class MergeValidatedLabelsTests(unittest.TestCase):
    def test_previous_manual_labels_are_transferred_by_page_key(self) -> None:
        merged, transferred = merge_validated_rows(
            _template_rows(),
            _validated_rows(),
        )

        row = merged[0]
        self.assertEqual(transferred, 3)
        self.assertEqual(row["page_type"], "blank")
        self.assertEqual(row["has_music"], "0")
        self.assertEqual(row["quality_comment"], "checked manually")

    def test_current_prediction_columns_stay_from_template(self) -> None:
        merged, _ = merge_validated_rows(
            _template_rows(),
            _validated_rows(),
        )

        row = merged[0]
        self.assertEqual(row["has_music_pred"], "1")
        self.assertEqual(row["has_music_score"], "0.95")
        self.assertEqual(row["image_path"], "new/page_001.png")

    def test_new_documents_keep_template_labels(self) -> None:
        merged, _ = merge_validated_rows(
            _template_rows(),
            _validated_rows(),
        )

        row = merged[1]
        self.assertEqual(row["page_type"], "music")
        self.assertEqual(row["has_music"], "1")
        self.assertEqual(row["quality_comment"], "")

    def test_validation_source_is_set_by_match_status(self) -> None:
        merged, _ = merge_validated_rows(
            _template_rows(),
            _validated_rows(),
        )

        self.assertEqual(merged[0]["validation_source"], "manual_previous")
        self.assertEqual(
            merged[1]["validation_source"],
            "template_prediction",
        )

    def test_needs_review_covers_unknown_uncertain_and_disagreement(self) -> None:
        merged, _ = merge_validated_rows(
            _template_rows(),
            _validated_rows(),
        )

        self.assertEqual(merged[0]["needs_review"], "1")
        self.assertEqual(merged[1]["needs_review"], "1")
        self.assertEqual(merged[2]["needs_review"], "1")
        self.assertEqual(merged[3]["needs_review"], "1")
        self.assertEqual(merged[4]["needs_review"], "0")

    def test_output_csv_has_expected_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            template_path = root / "template.csv"
            validated_path = root / "validated.csv"
            output_path = root / "pages_validated_thesis.csv"

            self._write_csv(
                template_path,
                REQUIRED_TEMPLATE_COLUMNS,
                _template_rows(),
            )
            self._write_csv(
                validated_path,
                REQUIRED_TEMPLATE_COLUMNS,
                _validated_rows(),
            )

            merge_validated_labels(
                template_path,
                validated_path,
                output_path,
            )

            with output_path.open(encoding="utf-8", newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                rows = list(reader)

            self.assertEqual(
                reader.fieldnames,
                REQUIRED_TEMPLATE_COLUMNS + ADDED_COLUMNS,
            )
            self.assertEqual(len(rows), len(_template_rows()))

    @staticmethod
    def _write_csv(
        path: Path,
        columns: list[str],
        rows: list[dict[str, str]],
    ) -> None:
        with path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
