"""Tests for the static OMR review demo."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "build_omr_review_demo.py"
SPEC = importlib.util.spec_from_file_location("build_omr_review_demo", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
demo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(demo)


class OmrReviewDemoTests(unittest.TestCase):
    def test_builds_expected_midi_path(self) -> None:
        path = demo.build_midi_path("rsl01", 7, Path("outputs/midi"))
        self.assertEqual(path, Path("outputs/midi/rsl01/page_007.mid"))

    def test_html_contains_page_files_and_review_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            image_path = root / "outputs" / "pages" / "doc-a" / "page_002.png"
            mxl_path = root / "outputs" / "omr" / "doc-a" / "page_002.mxl"
            midi_path = root / "outputs" / "midi" / "doc-a" / "page_002.mid"
            for path in (image_path, mxl_path, midi_path):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"file")
            output_path = root / "outputs" / "reports" / "demo.html"
            rows = [
                {
                    "doc_id": "doc-a",
                    "page_index": "2",
                    "page_type": "music",
                    "selection_reason": "manual",
                    "has_music_score": "0.95",
                    "image_path": "outputs/pages/doc-a/page_002.png",
                    "mxl_path": "outputs/omr/doc-a/page_002.mxl",
                }
            ]

            result = demo.build_omr_review_demo_html(
                rows,
                output_path,
                midi_dir=root / "outputs" / "midi",
                project_root=root,
            )

            self.assertIn("doc-a", result)
            self.assertIn("page_002.png", result)
            self.assertIn("Открыть скан", result)
            self.assertIn("Открыть MXL", result)
            self.assertIn("Открыть MIDI", result)
            self.assertIn("Пригодность", result)
            self.assertIn("Высота нот", result)
            self.assertIn("Длительности / ритм", result)
            self.assertIn("Общая оценка", result)
            self.assertIn("Комментарий эксперта", result)
            self.assertIn('data-field="usable"', result)
            self.assertIn('data-field="pitch_quality"', result)
            self.assertIn('data-field="duration_quality"', result)
            self.assertIn('data-field="overall_quality"', result)
            self.assertIn('data-field="expert_comment"', result)
            self.assertIn("localStorage", result)

    def test_missing_files_keep_review_card_visible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            result = demo.build_omr_review_demo_html(
                [
                    {
                        "doc_id": "doc-missing",
                        "page_index": "1",
                        "image_path": "missing/page.png",
                        "mxl_path": "missing/page.mxl",
                    }
                ],
                root / "reports" / "demo.html",
                midi_dir=root / "midi",
                project_root=root,
            )

            self.assertIn("doc-missing", result)
            self.assertIn("Файл PNG не найден", result)
            self.assertIn("Открыть MXL", result)
            self.assertIn("(файл не найден)", result)

    def test_html_contains_russian_instructions_and_rating_criteria(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            result = demo.build_omr_review_demo_html(
                [
                    {
                        "doc_id": "doc-a",
                        "page_index": "1",
                        "image_path": "page.png",
                        "mxl_path": "page.mxl",
                    }
                ],
                root / "demo.html",
                midi_dir=root / "midi",
                project_root=root,
            )

            self.assertIn("Сравните скан страницы с результатом MXL", result)
            self.assertIn("yes — можно использовать почти без", result)
            self.assertIn("5 — почти без ошибок", result)
            self.assertIn("ритм существенно нарушен", result)
            self.assertIn("5 — пригодно для дальнейшей работы", result)
            self.assertIn(
                "Встроенное воспроизведение MIDI будет добавлено позже",
                result,
            )


if __name__ == "__main__":
    unittest.main()
