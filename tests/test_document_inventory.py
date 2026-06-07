"""Tests for the thesis corpus document inventory."""

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd
import pymupdf
from pymarc import Field, Indicators, Record, Subfield

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_document_inventory import (
    INVENTORY_COLUMNS,
    build_document_inventory,
    write_document_inventory,
)


def _write_pdf(path: Path, pages_count: int = 2) -> None:
    document = pymupdf.open()
    for _ in range(pages_count):
        document.new_page()
    document.save(str(path))
    document.close()


def _write_mrc(path: Path) -> None:
    record = Record(force_utf8=True)
    record.add_field(
        Field(tag="001", data="record-001"),
        Field(
            tag="100",
            indicators=Indicators("1", " "),
            subfields=[Subfield("a", "Иванов, Иван")],
        ),
        Field(
            tag="245",
            indicators=Indicators("1", "0"),
            subfields=[Subfield("a", "Тестовая партитура")],
        ),
        Field(
            tag="264",
            indicators=Indicators(" ", "1"),
            subfields=[
                Subfield("a", "Москва"),
                Subfield("b", "Издательство"),
                Subfield("c", "2021"),
            ],
        ),
        Field(
            tag="041",
            indicators=Indicators("0", " "),
            subfields=[Subfield("a", "rus")],
        ),
        Field(
            tag="300",
            indicators=Indicators(" ", " "),
            subfields=[Subfield("a", "2 страницы")],
        ),
        Field(
            tag="856",
            indicators=Indicators("4", "0"),
            subfields=[Subfield("u", "https://example.org/record-001")],
        ),
    )
    path.write_bytes(record.as_marc())


class DocumentInventoryTests(unittest.TestCase):
    def test_builds_inventory_row_for_document_with_pdf_and_mrc(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            raw_dir = Path(temporary_dir) / "raw"
            document_dir = raw_dir / "rsl01000000001"
            document_dir.mkdir(parents=True)
            _write_pdf(document_dir / "document.pdf")
            _write_mrc(document_dir / "record.mrc")

            inventory = build_document_inventory(raw_dir)

            self.assertEqual(len(inventory), 1)
            row = inventory.iloc[0]
            self.assertEqual(row["doc_id"], "rsl01000000001")
            self.assertEqual(row["title"], "Тестовая партитура")
            self.assertEqual(row["authors"], "Иванов, Иван")
            self.assertEqual(str(row["year"]), "2021")
            self.assertEqual(row["language"], "rus")
            self.assertEqual(row["record_id"], "record-001")
            self.assertEqual(
                row["source_url"],
                "https://example.org/record-001",
            )
            self.assertEqual(row["pages_count"], 2)
            self.assertEqual(row["pdf_status"], "exists")
            self.assertEqual(row["mrc_status"], "parsed")

    def test_missing_pdf_does_not_stop_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            raw_dir = Path(temporary_dir) / "raw"
            document_dir = raw_dir / "rsl01000000001"
            document_dir.mkdir(parents=True)
            _write_mrc(document_dir / "record.mrc")

            row = build_document_inventory(raw_dir).iloc[0]

            self.assertEqual(row["pdf_status"], "missing")
            self.assertEqual(row["mrc_status"], "parsed")
            self.assertEqual(row["pages_count"], "")

    def test_missing_mrc_does_not_stop_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            raw_dir = Path(temporary_dir) / "raw"
            document_dir = raw_dir / "rsl01000000001"
            document_dir.mkdir(parents=True)
            _write_pdf(document_dir / "document.pdf", pages_count=1)

            row = build_document_inventory(raw_dir).iloc[0]

            self.assertEqual(row["pdf_status"], "exists")
            self.assertEqual(row["mrc_status"], "missing")
            self.assertEqual(row["pages_count"], 1)

    def test_output_csv_has_expected_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            raw_dir = root / "raw"
            (raw_dir / "rsl01000000001").mkdir(parents=True)
            output_path = root / "labels" / "document_inventory.csv"

            write_document_inventory(raw_dir, output_path)
            saved = pd.read_csv(output_path)

            self.assertTrue(output_path.is_file())
            self.assertEqual(list(saved.columns), INVENTORY_COLUMNS)


if __name__ == "__main__":
    unittest.main()
