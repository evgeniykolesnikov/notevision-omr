"""Tests for organizing downloaded RSL source files."""

import csv
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from notevision.metadata.file_matching import (
    detect_doc_id_from_filename,
    normalize_doc_id,
    organize_raw_files,
)


class FileMatchingTests(unittest.TestCase):
    def test_normalize_short_known_rsl_id(self) -> None:
        self.assertEqual(normalize_doc_id("004470876"), "rsl01004470876")

    def test_detect_doc_id_from_pdf(self) -> None:
        self.assertEqual(
            detect_doc_id_from_filename("rsl01004470876.pdf"),
            "rsl01004470876",
        )

    def test_detect_doc_id_from_mrc(self) -> None:
        self.assertEqual(
            detect_doc_id_from_filename("01004470876.mrc"),
            "rsl01004470876",
        )

    def test_import_pdf_and_mrc_pair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            inbox = root / "inbox"
            raw_dir = root / "raw"
            report_path = root / "reports" / "raw_import_report.csv"
            inbox.mkdir()
            (inbox / "rsl01004470876.pdf").write_bytes(b"pdf")
            (inbox / "01004470876.mrc").write_bytes(b"mrc")

            rows = organize_raw_files(
                inbox,
                raw_dir,
                report_path=report_path,
            )

            document_dir = raw_dir / "rsl01004470876"
            self.assertEqual(
                (document_dir / "rsl01004470876.pdf").read_bytes(),
                b"pdf",
            )
            self.assertEqual(
                (document_dir / "01004470876.mrc").read_bytes(),
                b"mrc",
            )
            source_text = (document_dir / "source.txt").read_text(
                encoding="utf-8"
            )
            self.assertIn("doc_id: rsl01004470876", source_text)
            self.assertFalse(any(row["status"] == "warning" for row in rows))

            with report_path.open(encoding="utf-8-sig", newline="") as report:
                report_rows = list(csv.DictReader(report))
            self.assertEqual(len(report_rows), 2)

    def test_import_only_mrc_adds_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            inbox = root / "inbox"
            raw_dir = root / "raw"
            inbox.mkdir()
            (inbox / "01004470876.mrc").write_bytes(b"mrc")

            rows = organize_raw_files(inbox, raw_dir)

            warnings = [row for row in rows if row["status"] == "warning"]
            self.assertEqual(len(warnings), 1)
            self.assertEqual(warnings[0]["file_type"], "pdf")
            self.assertIn("PDF file is missing", warnings[0]["message"])

    def test_existing_file_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            inbox = root / "inbox"
            raw_dir = root / "raw"
            document_dir = raw_dir / "rsl01004470876"
            inbox.mkdir()
            document_dir.mkdir(parents=True)
            (inbox / "rsl01004470876.pdf").write_bytes(b"new")
            target = document_dir / "rsl01004470876.pdf"
            target.write_bytes(b"existing")

            rows = organize_raw_files(inbox, raw_dir)

            self.assertEqual(target.read_bytes(), b"existing")
            import_row = next(
                row for row in rows if row["file_type"] == "pdf"
            )
            self.assertEqual(import_row["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
