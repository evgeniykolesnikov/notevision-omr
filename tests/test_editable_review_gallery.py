"""Tests for the static editable label review gallery."""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_editable_review_gallery import build_editable_review_gallery_html


class EditableReviewGalleryTests(unittest.TestCase):
    def _html(self) -> str:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            output_path = root / "outputs" / "reports" / "gallery.html"
            rows = [
                {
                    "doc_id": "doc-a",
                    "page_index": "7",
                    "image_path": "outputs/pages/doc-a/page_007.png",
                    "page_type": "unknown",
                    "has_music": "0",
                    "has_music_pred": "0",
                    "has_music_score": "0.5",
                    "validation_source": "template_prediction",
                    "needs_review": "1",
                    "review_reason": "unknown;uncertain_score",
                    "priority_group": "uncertain;unknown",
                    "quality_comment": '<script>alert("x")</script>',
                }
            ]
            return build_editable_review_gallery_html(
                rows,
                output_path,
                project_root=root,
            )

    def test_gallery_contains_page_type_select(self) -> None:
        gallery = self._html()

        self.assertIn('<select class="page-type">', gallery)
        self.assertIn('"music"', gallery)
        self.assertIn('"unknown"', gallery)

    def test_gallery_contains_export_corrections_button(self) -> None:
        gallery = self._html()

        self.assertIn("Export corrections CSV", gallery)
        self.assertIn("thesis_label_corrections.csv", gallery)
        self.assertIn("Export JSON", gallery)
        self.assertIn("thesis_label_corrections.json", gallery)

    def test_gallery_escapes_comments_and_shows_missing_image_warning(self) -> None:
        gallery = self._html()

        self.assertNotIn('<script>alert("x")</script>', gallery)
        self.assertIn("\\u003cscript\\u003ealert", gallery)
        self.assertIn("Image file not found", gallery)

    def test_gallery_contains_autosave_pagination_and_document_filter(self) -> None:
        gallery = self._html()

        self.assertIn("localStorage.setItem", gallery)
        self.assertIn("localStorage.getItem", gallery)
        self.assertIn('id="page-size"', gallery)
        self.assertIn('<option value="50">50</option>', gallery)
        self.assertIn('<option value="100">100</option>', gallery)
        self.assertIn('<option value="200">200</option>', gallery)
        self.assertIn('id="document-filter"', gallery)
        self.assertIn("All documents", gallery)

    def test_gallery_contains_quick_actions_and_automatic_changed(self) -> None:
        gallery = self._html()

        for label in ["Music", "Title", "Text", "Blank", "Bad Scan"]:
            self.assertIn(f">{label}</button>", gallery)
        self.assertIn("function markChanged", gallery)
        self.assertIn("changed: true", gallery)
        self.assertIn("quality-comment", gallery)


if __name__ == "__main__":
    unittest.main()
