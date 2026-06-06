"""Tests for PDF page extraction."""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from notevision.pdf.extract_pages import (
    extract_pdf_pages,
    find_pdf_in_document_dir,
)


class ExtractPdfPagesTests(unittest.TestCase):
    def test_extract_pdf_pages_exists(self) -> None:
        self.assertTrue(callable(extract_pdf_pages))

    def test_extract_pdf_pages_rejects_missing_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            missing_pdf = root / "missing.pdf"

            with self.assertRaisesRegex(
                FileNotFoundError, "PDF file does not exist"
            ):
                extract_pdf_pages(missing_pdf, root / "pages")

    def test_find_pdf_in_document_dir_returns_single_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            document_dir = Path(temporary_dir)
            pdf_path = document_dir / "original_name.pdf"
            pdf_path.touch()
            (document_dir / "metadata.mrc").touch()
            (document_dir / "source.txt").touch()

            self.assertEqual(find_pdf_in_document_dir(document_dir), pdf_path)

    def test_find_pdf_in_document_dir_rejects_missing_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            document_dir = Path(temporary_dir)
            (document_dir / "source.txt").touch()

            with self.assertRaisesRegex(FileNotFoundError, "No PDF file found"):
                find_pdf_in_document_dir(document_dir)

    def test_find_pdf_in_document_dir_rejects_multiple_pdfs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            document_dir = Path(temporary_dir)
            first_pdf = document_dir / "first.pdf"
            second_pdf = document_dir / "second.pdf"
            first_pdf.touch()
            second_pdf.touch()

            with self.assertRaisesRegex(
                ValueError, r"Multiple PDF files found.*first\.pdf.*second\.pdf"
            ):
                find_pdf_in_document_dir(document_dir)


if __name__ == "__main__":
    unittest.main()
