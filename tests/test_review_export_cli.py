"""Tests for the read-only expert review CSV exporter."""

from __future__ import annotations

import csv
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from review_app.database import get_or_create_reviewer, init_db, save_review
from review_app.export_csv import EXPORT_FIELDS, export_reviews, main
from review_app.import_package import import_package
from review_app.schemas import validate_review_submission


def create_package(package_dir: Path) -> None:
    package_dir.mkdir()
    prefix = "01_rsl01000000001_page_001"
    (package_dir / f"{prefix}_scan.png").write_bytes(b"png")
    (package_dir / f"{prefix}_audio.mp3").write_bytes(b"audio")


class ReviewExportCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_dir.name)
        self.db_path = self.root / "review.db"
        package_dir = self.root / "package"
        create_package(package_dir)
        import_package(package_dir, self.db_path)
        self.alex, _ = get_or_create_reviewer(self.db_path, "Алексей")
        self.maria, _ = get_or_create_reviewer(self.db_path, "Мария")
        self._save(self.alex, "completed", "yes")
        self._save(self.maria, "draft", "partial")

    def tearDown(self) -> None:
        self.temporary_dir.cleanup()

    def _save(
        self,
        reviewer: dict[str, object],
        status: str,
        usable: str,
    ) -> None:
        submission, errors = validate_review_submission(
            {"page_usable": usable, "usability_score": "4"},
            complete=status == "completed",
            reviewer=str(reviewer["name"]),
            review_date="2026-06-09" if status == "completed" else "",
        )
        self.assertEqual(errors, [])
        save_review(
            self.db_path,
            1,
            int(reviewer["id"]),
            submission.as_dict(),
            status,
        )

    def test_export_creates_expected_columns(self) -> None:
        output = self.root / "nested" / "reviews.csv"
        count = export_reviews(self.db_path, output)

        self.assertEqual(count, 2)
        with output.open(encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            rows = list(reader)
        self.assertEqual(tuple(reader.fieldnames or ()), EXPORT_FIELDS)
        self.assertEqual({row["review_status"] for row in rows}, {"completed", "draft"})
        self.assertEqual(rows[0]["item_number"], "1")
        self.assertTrue(rows[0]["review_id"])

    def test_completed_only_and_exclude_reviewer(self) -> None:
        completed_path = self.root / "completed.csv"
        self.assertEqual(
            export_reviews(
                self.db_path,
                completed_path,
                completed_only=True,
            ),
            1,
        )
        excluded_path = self.root / "excluded.csv"
        self.assertEqual(
            export_reviews(
                self.db_path,
                excluded_path,
                exclude_reviewers=["  алексей "],
            ),
            1,
        )
        with excluded_path.open(encoding="utf-8-sig", newline="") as csv_file:
            rows = list(csv.DictReader(csv_file))
        self.assertEqual(rows[0]["reviewer"], "Мария")

    def test_empty_database_exports_header(self) -> None:
        empty_db = self.root / "empty.db"
        init_db(empty_db)
        output = self.root / "empty.csv"

        self.assertEqual(export_reviews(empty_db, output), 0)
        with output.open(encoding="utf-8-sig", newline="") as csv_file:
            rows = list(csv.DictReader(csv_file))
        self.assertEqual(rows, [])

    def test_cli_creates_output_and_prints_count(self) -> None:
        output = self.root / "cli" / "reviews.csv"
        stdout = io.StringIO()
        with patch.object(
            sys,
            "argv",
            [
                "review_app.export_csv",
                "--db",
                str(self.db_path),
                "--out",
                str(output),
                "--completed-only",
            ],
        ), redirect_stdout(stdout):
            main()

        self.assertTrue(output.is_file())
        self.assertIn("Exported reviews: 1", stdout.getvalue())
        self.assertIn(str(output), stdout.getvalue())

    def test_export_excludes_igor_without_deleting_review(self) -> None:
        igor, _ = get_or_create_reviewer(self.db_path, "Igor")
        self._save(igor, "completed", "no")
        output = self.root / "without-igor.csv"

        count = export_reviews(
            self.db_path,
            output,
            exclude_reviewers=["Igor"],
        )

        self.assertEqual(count, 2)
        with output.open(encoding="utf-8-sig", newline="") as csv_file:
            rows = list(csv.DictReader(csv_file))
        self.assertNotIn("Igor", {row["reviewer"] for row in rows})


if __name__ == "__main__":
    unittest.main()
