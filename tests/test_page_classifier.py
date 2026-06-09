"""Tests for the trainable page-classifier baselines."""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from predict_page_classifier import (  # noqa: E402
    discover_pages,
    predict_classical,
    write_predictions,
)
from train_page_classifier import write_metrics_report  # noqa: E402
from notevision.page_classifier.classical import (  # noqa: E402
    save_classical_artifact,
    train_classical_models,
)
from notevision.page_classifier.dataset import (  # noqa: E402
    PageRecord,
    build_page_records,
    split_by_document,
)
from notevision.page_classifier.features import (  # noqa: E402
    FEATURE_NAMES,
    extract_classical_features,
)


class TinyEstimator:
    def fit(self, features: list[list[float]], labels: list[int]) -> "TinyEstimator":
        grouped = {
            label: [
                row[2] for row, current_label in zip(features, labels)
                if current_label == label
            ]
            for label in set(labels)
        }
        self.threshold = (
            sum(grouped[min(grouped)]) / len(grouped[min(grouped)])
            + sum(grouped[max(grouped)]) / len(grouped[max(grouped)])
        ) / 2
        return self

    def predict(self, features: list[list[float]]) -> list[int]:
        return [int(row[2] >= self.threshold) for row in features]

    def predict_proba(self, features: list[list[float]]) -> list[list[float]]:
        return [
            [0.9, 0.1] if prediction == 0 else [0.1, 0.9]
            for prediction in self.predict(features)
        ]


def make_image(path: Path, *, music: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 160, 220
    pixels = [255] * (width * height)
    if music:
        for staff_start in (45, 115):
            for offset in range(5):
                y = staff_start + offset * 5
                for x in range(12, 149):
                    pixels[y * width + x] = 0
        for x in range(25, 145, 20):
            for y in range(52, 59):
                for note_x in range(x, x + 7):
                    pixels[y * width + note_x] = 0
    path.write_bytes(
        f"P5\n{width} {height}\n255\n".encode("ascii") + bytes(pixels)
    )


def write_labels(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


class PageClassifierTests(unittest.TestCase):
    def test_dataset_filters_only_manual_labels(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            labels = root / "data" / "labels" / "pages.csv"
            pages = root / "outputs" / "pages"
            make_image(pages / "rsl001" / "page_001.png", music=True)
            make_image(pages / "rsl002" / "page_001.png", music=False)
            write_labels(
                labels,
                [
                    {
                        "doc_id": "rsl001",
                        "page_index": 1,
                        "page_type": "music",
                        "has_music": 1,
                        "image_path": "",
                        "validation_source": "manual_thesis",
                        "has_music_pred": 1,
                    },
                    {
                        "doc_id": "rsl002",
                        "page_index": 1,
                        "page_type": "title",
                        "has_music": 0,
                        "image_path": "",
                        "validation_source": "template_prediction",
                        "has_music_pred": 0,
                    },
                ],
            )

            records = build_page_records(labels, pages)

            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].validation_source, "manual_thesis")

    def test_split_has_no_document_overlap(self) -> None:
        records = [
            PageRecord(
                doc_id=f"rsl00{doc}",
                page_index=page,
                image_path=Path("missing.png"),
                target=page % 2,
                page_type="music",
                has_music=page % 2,
                validation_source="manual_previous",
            )
            for doc in range(4)
            for page in range(1, 4)
        ]

        train, validation = split_by_document(
            records, validation_fraction=0.25, random_seed=42
        )

        self.assertTrue(train)
        self.assertTrue(validation)
        self.assertFalse(
            {record.doc_id for record in train}
            & {record.doc_id for record in validation}
        )

    def test_classical_features_extract_from_tiny_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "page.pgm"
            make_image(path, music=True)

            features = extract_classical_features(path)

            self.assertEqual(set(features), set(FEATURE_NAMES))
            self.assertGreater(features["black_pixel_ratio"], 0)
            self.assertGreater(features["horizontal_line_density"], 0)

    def test_classical_training_and_missing_image_are_resilient(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            train_records = []
            validation_records = []
            for index, music in enumerate((False, True, False, True), start=1):
                path = root / f"train_{index}.pgm"
                make_image(path, music=music)
                train_records.append(
                    PageRecord(
                        "rsl001",
                        index,
                        path,
                        int(music),
                        "music" if music else "blank",
                        int(music),
                        "manual_thesis",
                    )
                )
            for index, music in enumerate((False, True), start=1):
                path = root / f"val_{index}.pgm"
                make_image(path, music=music)
                validation_records.append(
                    PageRecord(
                        "rsl002",
                        index,
                        path,
                        int(music),
                        "music" if music else "blank",
                        int(music),
                        "manual_thesis",
                    )
                )
            validation_records.append(
                PageRecord(
                    "rsl002",
                    3,
                    root / "missing.png",
                    1,
                    "music",
                    1,
                    "manual_thesis",
                )
            )

            result = train_classical_models(
                train_records,
                validation_records,
                estimators={"tiny": TinyEstimator()},
            )

            self.assertEqual(result["selected_name"], "tiny")
            self.assertEqual(result["selected"]["metrics"]["f1"], 1.0)
            self.assertEqual(len(result["errors"]), 1)

    def test_metrics_and_prediction_csv_are_created(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            metrics_path = root / "metrics.md"
            write_metrics_report(
                metrics_path,
                records_count=4,
                document_count=2,
                train_documents=["rsl001"],
                validation_documents=["rsl002"],
                target="has_music",
                model="classical/tiny",
                metrics={
                    "accuracy": 1.0,
                    "precision": 1.0,
                    "recall": 1.0,
                    "f1": 1.0,
                    "labels": ["0", "1"],
                    "confusion_matrix": {
                        "0": {"0": 1, "1": 0},
                        "1": {"0": 0, "1": 1},
                    },
                },
                epochs="not applicable",
                augmentations="none",
                errors_count=0,
                comparison="Comparable.",
            )
            pages = root / "pages"
            image_path = pages / "rsl001" / "page_001.pgm"
            make_image(image_path, music=True)
            model_path = root / "model.joblib"
            estimator = TinyEstimator()
            estimator.threshold = 0.01
            save_classical_artifact(
                model_path,
                {"kind": "classical", "model": estimator, "target": "has_music"},
            )

            records = discover_pages(pages)
            rows = predict_classical(model_path, records)
            output = root / "predictions.csv"
            write_predictions(output, rows)

            self.assertTrue(metrics_path.is_file())
            self.assertIn("document-level", metrics_path.read_text(encoding="utf-8"))
            self.assertTrue(output.is_file())
            with output.open(encoding="utf-8", newline="") as csv_file:
                saved = list(csv.DictReader(csv_file))
            self.assertEqual(saved[0]["status"], "success")
            self.assertEqual(saved[0]["doc_id"], "rsl001")


if __name__ == "__main__":
    unittest.main()
