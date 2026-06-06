"""Tests for MRC metadata parsing."""

import sys
import tempfile
import unittest
from pathlib import Path

from pymarc import Field, Indicators, Record, Subfield

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from notevision.metadata.parse_mrc import (
    find_mrc_in_document_dir,
    parse_mrc_file,
)


class MrcMetadataTests(unittest.TestCase):
    def test_find_mrc_in_document_dir_returns_single_mrc(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            document_dir = Path(temporary_dir)
            mrc_path = document_dir / "original_record.mrc"
            mrc_path.touch()
            (document_dir / "document.pdf").touch()

            self.assertEqual(find_mrc_in_document_dir(document_dir), mrc_path)

    def test_find_mrc_in_document_dir_rejects_missing_mrc(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            document_dir = Path(temporary_dir)

            with self.assertRaisesRegex(FileNotFoundError, "No MRC file found"):
                find_mrc_in_document_dir(document_dir)

    def test_find_mrc_in_document_dir_rejects_multiple_mrc_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            document_dir = Path(temporary_dir)
            (document_dir / "first.mrc").touch()
            (document_dir / "second.mrc").touch()

            with self.assertRaisesRegex(
                ValueError, r"Multiple MRC files found.*first\.mrc.*second\.mrc"
            ):
                find_mrc_in_document_dir(document_dir)

    def test_parse_mrc_file_reads_minimal_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            document_dir = Path(temporary_dir) / "rsl-test"
            document_dir.mkdir()
            mrc_path = document_dir / "record.mrc"

            record = Record(force_utf8=True)
            record.add_field(
                Field(tag="001", data="record-001"),
                Field(
                    tag="008",
                    data="240101s2020    ru ||||| |||||000|0|rus|d",
                ),
                Field(
                    tag="100",
                    indicators=Indicators("1", " "),
                    subfields=[Subfield("a", "Иванов, Иван")],
                ),
                Field(
                    tag="245",
                    indicators=Indicators("1", "0"),
                    subfields=[
                        Subfield("a", "Тестовая партитура"),
                        Subfield("b", "ноты"),
                    ],
                ),
                Field(
                    tag="264",
                    indicators=Indicators(" ", "1"),
                    subfields=[
                        Subfield("a", "Москва"),
                        Subfield("b", "Издательство"),
                        Subfield("c", "2020"),
                    ],
                ),
                Field(
                    tag="041",
                    indicators=Indicators("0", " "),
                    subfields=[Subfield("a", "rus")],
                ),
                Field(
                    tag="856",
                    indicators=Indicators("4", "0"),
                    subfields=[Subfield("u", "https://example.org/record-001")],
                ),
            )
            mrc_path.write_bytes(record.as_marc())

            metadata = parse_mrc_file(mrc_path)

            self.assertEqual(metadata["doc_id"], "rsl-test")
            self.assertEqual(metadata["title"], "Тестовая партитура ноты")
            self.assertEqual(metadata["authors"], ["Иванов, Иван"])
            self.assertEqual(metadata["year"], "2020")
            self.assertEqual(metadata["language"], "rus")
            self.assertEqual(metadata["record_id"], "record-001")
            self.assertEqual(
                metadata["electronic_resources"],
                ["https://example.org/record-001"],
            )
            self.assertIn("245", metadata["raw_fields_summary"])


if __name__ == "__main__":
    unittest.main()
