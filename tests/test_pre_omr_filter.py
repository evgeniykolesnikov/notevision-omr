"""Tests for the experimental pre-OMR filter."""

import tempfile
import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

try:
    import cv2
    import numpy as np

    from notevision.omr.pre_omr_filter import (
        classify_pre_omr,
        evaluate_against_labels,
        extract_pre_omr_features,
        run_pre_omr_filter,
    )
except Exception as import_error:  # pragma: no cover - environment guard
    cv2 = None
    np = None
    classify_pre_omr = None
    evaluate_against_labels = None
    extract_pre_omr_features = None
    run_pre_omr_filter = None
    IMPORT_ERROR = import_error
else:
    IMPORT_ERROR = None


class PreOmrFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        if IMPORT_ERROR is not None:
            self.skipTest(f"OpenCV/NumPy are unavailable: {IMPORT_ERROR}")

    def test_blank_page_is_filtered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            image_path = Path(temporary_dir) / "blank.png"
            image = np.full((200, 300), 255, dtype=np.uint8)
            self.assertTrue(cv2.imwrite(str(image_path), image))

            features = extract_pre_omr_features(image_path)
            decision = classify_pre_omr(features)

        self.assertLess(features["dark_pixel_ratio"], 0.01)
        self.assertFalse(decision["send_to_omr"])
        self.assertEqual(decision["predicted_non_music_reason"], "blank")

    def test_staff_like_page_is_kept_for_omr(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            image_path = Path(temporary_dir) / "staff.png"
            image = np.full((240, 420), 255, dtype=np.uint8)
            for group_y in (60, 145):
                for offset in range(0, 50, 10):
                    cv2.line(
                        image,
                        (35, group_y + offset),
                        (385, group_y + offset),
                        0,
                        1,
                    )
            self.assertTrue(cv2.imwrite(str(image_path), image))

            features = extract_pre_omr_features(image_path)
            decision = classify_pre_omr(features)

        self.assertGreaterEqual(features["staff_line_candidate_count"], 10)
        self.assertTrue(decision["send_to_omr"])

    def test_text_like_page_is_filtered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            image_path = Path(temporary_dir) / "text.png"
            image = np.full((260, 360), 255, dtype=np.uint8)
            for row in range(25, 225, 18):
                for column in range(30, 300, 28):
                    cv2.rectangle(
                        image,
                        (column, row),
                        (column + 12, row + 8),
                        0,
                        -1,
                    )
            self.assertTrue(cv2.imwrite(str(image_path), image))

            features = extract_pre_omr_features(image_path)
            decision = classify_pre_omr(features)

        self.assertGreater(features["estimated_text_density"], 450)
        self.assertFalse(decision["send_to_omr"])
        self.assertEqual(decision["predicted_non_music_reason"], "text")

    def test_evaluation_counts_false_positive_and_music_losses(self) -> None:
        predictions = [
            {
                "doc_id": "rsl001",
                "page_index": 1,
                "send_to_omr": False,
                "predicted_non_music_reason": "title",
            },
            {
                "doc_id": "rsl001",
                "page_index": 2,
                "send_to_omr": True,
                "predicted_non_music_reason": "unknown",
            },
            {
                "doc_id": "rsl001",
                "page_index": 3,
                "send_to_omr": False,
                "predicted_non_music_reason": "decorative",
            },
        ]
        candidates = [
            {"doc_id": "rsl001", "page_index": "1", "page_type": "title"},
            {"doc_id": "rsl001", "page_index": "2", "page_type": "music"},
            {"doc_id": "rsl001", "page_index": "3", "page_type": "mixed"},
        ]
        failure_review = [
            {
                "doc_id": "rsl001",
                "page_index": "1",
                "classifier_error_type": "false_positive_music",
                "corrected_has_music": "false",
                "should_send_to_omr": "false",
            }
        ]

        metrics = evaluate_against_labels(
            predictions,
            candidates,
            failure_review,
        )

        self.assertEqual(metrics["false_positive_music_total"], 1)
        self.assertEqual(metrics["false_positive_music_filtered"], 1)
        self.assertEqual(metrics["music_mixed_total"], 2)
        self.assertEqual(metrics["music_mixed_wrongly_filtered"], 1)

    def test_run_filter_resolves_pages_dir_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            pages_dir = root / "outputs" / "pages"
            image_path = pages_dir / "rsl001" / "page_001.png"
            image_path.parent.mkdir(parents=True)
            image = np.full((120, 160), 255, dtype=np.uint8)
            self.assertTrue(cv2.imwrite(str(image_path), image))

            rows = run_pre_omr_filter(
                [{"doc_id": "rsl001", "page_index": "1"}],
                pages_dir=pages_dir,
                project_root=root,
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["doc_id"], "rsl001")
        self.assertFalse(rows[0]["send_to_omr"])


if __name__ == "__main__":
    unittest.main()
