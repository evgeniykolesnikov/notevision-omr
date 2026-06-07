"""Tests for high-resolution extraction of OMR candidate pages."""

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from extract_omr_pages import extract_omr_candidate_pages


def _candidates() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "doc_id": ["doc-a", "doc-a", "doc-b"],
            "page_index": [2, 4, 1],
            "page_type": ["music", "music", "music"],
            "has_music": [1, 1, 1],
            "image_path": ["a2.png", "a4.png", "b1.png"],
            "preprocessed_path": ["pa2.png", "pa4.png", "pb1.png"],
            "quality_comment": ["", "", ""],
            "exists": [True, True, True],
        }
    )


class FakePixmap:
    def __init__(self, page_number: int, saved_pages: list[int]) -> None:
        self.page_number = page_number
        self.saved_pages = saved_pages

    def save(self, output_path: str) -> None:
        destination = Path(output_path)
        destination.write_bytes(f"page-{self.page_number}".encode())
        self.saved_pages.append(self.page_number)


class FakePage:
    def __init__(self, page_number: int, saved_pages: list[int]) -> None:
        self.page_number = page_number
        self.saved_pages = saved_pages

    def get_pixmap(self, dpi: int, alpha: bool) -> FakePixmap:
        return FakePixmap(self.page_number, self.saved_pages)


class FakeDocument:
    def __init__(self, page_count: int, saved_pages: list[int]) -> None:
        self.page_count = page_count
        self.saved_pages = saved_pages

    def __enter__(self) -> "FakeDocument":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def __len__(self) -> int:
        return self.page_count

    def __getitem__(self, index: int) -> FakePage:
        return FakePage(index + 1, self.saved_pages)


class ExtractOmrPagesTests(unittest.TestCase):
    def test_extracts_only_candidate_pages_and_builds_output_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            raw_dir = root / "raw"
            output_dir = root / "omr_pages"
            for doc_id in ("doc-a", "doc-b"):
                document_dir = raw_dir / doc_id
                document_dir.mkdir(parents=True)
                (document_dir / f"{doc_id}.pdf").touch()

            saved_pages: list[int] = []

            def fake_opener(pdf_path: Path) -> FakeDocument:
                return FakeDocument(5, saved_pages)

            report = extract_omr_candidate_pages(
                _candidates(),
                raw_dir,
                output_dir,
                dpi=300,
                pdf_opener=fake_opener,
            )

            self.assertEqual(saved_pages, [2, 4, 1])
            self.assertEqual((report["status"] == "success").sum(), 3)
            expected = output_dir / "doc-a" / "page_002.png"
            self.assertTrue(expected.is_file())
            self.assertEqual(report.iloc[0]["output_path"], str(expected))
            self.assertFalse(
                (output_dir / "doc-a" / "page_001.png").exists()
            )

    def test_limit_restricts_extracted_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            raw_dir = root / "raw"
            output_dir = root / "omr_pages"
            document_dir = raw_dir / "doc-a"
            document_dir.mkdir(parents=True)
            (document_dir / "doc-a.pdf").touch()
            saved_pages: list[int] = []

            report = extract_omr_candidate_pages(
                _candidates(),
                raw_dir,
                output_dir,
                limit=1,
                pdf_opener=lambda _: FakeDocument(5, saved_pages),
            )

            self.assertEqual(len(report), 1)
            self.assertEqual(saved_pages, [2])
            self.assertEqual(
                report.iloc[0]["output_path"],
                str(output_dir / "doc-a" / "page_002.png"),
            )


if __name__ == "__main__":
    unittest.main()
