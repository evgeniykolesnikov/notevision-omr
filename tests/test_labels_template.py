"""Tests for manual labels template generation."""

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_labels_template import (
    OUTPUT_COLUMNS,
    build_labels_template,
    write_labels_template,
)


def _predictions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "doc_id": ["doc-a", "doc-a", "doc-a", "doc-b", "doc-b"],
            "page_index": [1, 2, 3, 1, 2],
            "image_path": [
                "a/page_001.png",
                "a/page_002.png",
                "a/page_003.png",
                "b/page_001.png",
                "b/page_002.png",
            ],
            "has_music_pred": [1, 0, 1, 0, 1],
            "has_music_score": [0.9, 0.1, 0.8, 0.2, 0.7],
        }
    )


class LabelsTemplateTests(unittest.TestCase):
    def test_build_template_from_small_dataframe(self) -> None:
        template = build_labels_template(_predictions())

        self.assertEqual(list(template.columns), OUTPUT_COLUMNS)
        self.assertEqual(len(template), 5)
        self.assertListEqual(
            template["has_music"].tolist(),
            template["has_music_pred"].tolist(),
        )
        self.assertTrue((template["quality_comment"] == "").all())

    def test_page_type_is_derived_from_prediction(self) -> None:
        template = build_labels_template(_predictions())

        self.assertEqual(
            template["page_type"].tolist(),
            ["music", "unknown", "music", "unknown", "music"],
        )

    def test_existing_output_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            predictions_path = root / "predictions.csv"
            output_path = root / "pages_template.csv"
            _predictions().to_csv(predictions_path, index=False)
            output_path.write_text("existing", encoding="utf-8")

            with self.assertRaisesRegex(
                FileExistsError,
                r"already exists.*--overwrite",
            ):
                write_labels_template(predictions_path, output_path)

            self.assertEqual(
                output_path.read_text(encoding="utf-8"),
                "existing",
            )

    def test_sample_only_selects_first_pages_per_document(self) -> None:
        template = build_labels_template(_predictions(), sample_only=2)

        self.assertEqual(len(template), 4)
        self.assertEqual(
            list(zip(template["doc_id"], template["page_index"])),
            [("doc-a", 1), ("doc-a", 2), ("doc-b", 1), ("doc-b", 2)],
        )


if __name__ == "__main__":
    unittest.main()
