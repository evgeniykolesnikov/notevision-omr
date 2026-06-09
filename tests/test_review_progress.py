"""Tests for expert review progress monitoring."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from review_app.database import get_or_create_reviewer, save_review
from review_app.import_package import import_package
from review_app.schemas import validate_review_submission
from scripts.review_progress import build_markdown, collect_review_progress


class ReviewProgressTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_dir.name)
        package_dir = self.root / "package"
        package_dir.mkdir()
        for number in (1, 2):
            prefix = f"{number:02d}_rsl001_page_{number:03d}"
            (package_dir / f"{prefix}_scan.png").write_bytes(b"png")
            (package_dir / f"{prefix}_audio.mp3").write_bytes(b"audio")
        self.db_path = self.root / "review.db"
        import_package(package_dir, self.db_path)
        self.alex, _ = get_or_create_reviewer(self.db_path, "Алексей")
        self.maria, _ = get_or_create_reviewer(self.db_path, "Мария")
        self._save(1, self.alex, "completed")
        self._save(2, self.alex, "draft")

    def tearDown(self) -> None:
        self.temporary_dir.cleanup()

    def _save(
        self,
        item_number: int,
        reviewer: dict[str, object],
        status: str,
    ) -> None:
        submission, errors = validate_review_submission(
            {"page_usable": "yes"},
            complete=status == "completed",
            reviewer=str(reviewer["name"]),
            review_date="2026-06-09" if status == "completed" else "",
        )
        self.assertEqual(errors, [])
        save_review(
            self.db_path,
            item_number,
            int(reviewer["id"]),
            submission.as_dict(),
            status,
        )

    def test_counts_progress_and_exclusion(self) -> None:
        rows = collect_review_progress(self.db_path, total=2)
        alex = next(row for row in rows if row["reviewer"] == "Алексей")
        self.assertEqual(alex["completed"], 1)
        self.assertEqual(alex["draft"], 1)
        self.assertEqual(alex["filled"], 2)
        self.assertEqual(alex["progress"], 1.0)

        filtered = collect_review_progress(
            self.db_path,
            total=2,
            exclude_reviewers=["алексей"],
        )
        self.assertNotIn("Алексей", {row["reviewer"] for row in filtered})

    def test_markdown_contains_table(self) -> None:
        markdown = build_markdown(
            collect_review_progress(self.db_path, total=30),
            30,
        )
        self.assertIn("| Reviewer | Completed |", markdown)
        self.assertIn("Алексей", markdown)
        self.assertIn("6.7%", markdown)

    def test_progress_excludes_igor(self) -> None:
        igor, _ = get_or_create_reviewer(self.db_path, "Igor")
        self._save(1, igor, "completed")

        rows = collect_review_progress(
            self.db_path,
            total=30,
            exclude_reviewers=["Igor"],
        )

        self.assertNotIn("Igor", {row["reviewer"] for row in rows})


if __name__ == "__main__":
    unittest.main()
