"""Tests for the protected OMR expert review web application."""

import csv
import importlib.util
import io
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path

from review_app.auth import build_reviewer_session, read_reviewer_session
from review_app.database import (
    connect,
    get_item,
    get_or_create_local_reviewer,
    get_or_create_reviewer,
    get_review,
    init_db,
    list_items,
    save_review,
)
from review_app.export_csv import build_export_csv
from review_app.import_package import discover_package_items, import_package
from review_app.schemas import resolve_review_metadata, validate_review_submission


def web_tests_available() -> bool:
    if not all(
        importlib.util.find_spec(module)
        for module in ("fastapi", "httpx", "jinja2")
    ):
        return False
    try:
        import fastapi  # noqa: F401
        import httpx  # noqa: F401
        import jinja2  # noqa: F401
    except Exception:
        return False
    return True


WEB_TESTS_AVAILABLE = web_tests_available()


def create_package(package_dir: Path, item_count: int = 2) -> None:
    package_dir.mkdir()
    for item_number in range(1, item_count + 1):
        prefix = (
            f"{item_number:02d}_rsl0100000000{item_number}_"
            f"page_{item_number:03d}"
        )
        (package_dir / f"{prefix}_scan.png").write_bytes(b"png")
        (package_dir / f"{prefix}_audio.mp3").write_bytes(b"audio")
        for track_number in range(1, item_number + 1):
            (
                package_dir
                / f"{prefix}_track_{track_number:02d}.mp3"
            ).write_bytes(b"track")


class ReviewAppCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_dir.name)
        self.package_dir = self.root / "package"
        self.db_path = self.root / "review.db"
        create_package(self.package_dir)
        import_package(self.package_dir, self.db_path)
        self.reviewer_a, _ = get_or_create_reviewer(
            self.db_path,
            "Алексей",
        )
        self.reviewer_b, _ = get_or_create_reviewer(
            self.db_path,
            "Мария",
        )

    def tearDown(self) -> None:
        self.temporary_dir.cleanup()

    def test_import_package_discovers_items_and_tracks(self) -> None:
        items = discover_package_items(self.package_dir)

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["item_number"], 1)
        self.assertEqual(items[0]["doc_id"], "rsl01000000001")
        self.assertTrue(str(items[0]["scan_path"]).endswith("_scan.png"))
        self.assertEqual(len(items[1]["track_paths"]), 2)
        stored = get_item(
            self.db_path,
            2,
            int(self.reviewer_a["id"]),
        )
        self.assertEqual(stored["review_status"], "not_reviewed")
        self.assertEqual(stored["review_set"], "default")

    def test_validation_rejects_inconsistent_counters(self) -> None:
        _, errors = validate_review_submission(
            {
                "checked_measures": "2",
                "correct_measures": "3",
                "reference_notes": "4",
                "matched_notes": "5",
                "pitch_errors": "-1",
            },
            complete=False,
            reviewer="Эксперт",
        )

        self.assertTrue(
            any("корректных тактов" in error for error in errors)
        )
        self.assertTrue(
            any("сопоставленных нот" in error for error in errors)
        )
        self.assertTrue(any("отрицательным" in error for error in errors))

    def test_saves_draft(self) -> None:
        submission, errors = validate_review_submission(
            {
                "checked_measures": "5",
                "correct_measures": "4",
                "reference_notes": "20",
                "matched_notes": "18",
                "pitch_errors": "1",
                "requires_new_omr": "1",
            },
            complete=False,
            reviewer="Музыкант",
        )
        self.assertEqual(errors, [])

        save_review(
            self.db_path,
            1,
            int(self.reviewer_a["id"]),
            submission.as_dict(),
            "draft",
        )

        item = get_item(
            self.db_path,
            1,
            int(self.reviewer_a["id"]),
        )
        self.assertEqual(item["review_status"], "draft")
        self.assertEqual(item["reviewer"], "Музыкант")
        self.assertEqual(item["checked_measures"], 5)
        self.assertEqual(item["requires_new_omr"], 1)

    def test_complete_review_requires_and_saves_required_fields(self) -> None:
        submission, errors = validate_review_submission(
            {
                "page_usable": "partial",
                "usability_score": "3",
                "rhythm_problem": "1",
                "expert_comment": "Нужна небольшая правка.",
            },
            complete=True,
            reviewer="Эксперт",
            review_date="2026-06-09",
        )
        self.assertEqual(errors, [])
        save_review(
            self.db_path,
            1,
            int(self.reviewer_a["id"]),
            submission.as_dict(),
            "completed",
        )

        item = get_item(
            self.db_path,
            1,
            int(self.reviewer_a["id"]),
        )
        self.assertEqual(item["review_status"], "completed")
        self.assertEqual(item["page_usable"], "partial")
        self.assertEqual(item["usability_score"], 3)
        self.assertEqual(item["rhythm_problem"], 1)
        self.assertEqual(item["checked_measures"], 0)
        self.assertIsNotNone(item["updated_at"])

    def test_counter_relations_are_checked_only_when_both_are_filled(self) -> None:
        _, errors = validate_review_submission(
            {
                "page_usable": "yes",
                "correct_measures": "8",
                "matched_notes": "20",
            },
            complete=True,
            reviewer="Эксперт",
            review_date="2026-06-09",
        )
        self.assertEqual(errors, [])

    def test_reviewer_cookie_contains_signed_id(self) -> None:
        token = build_reviewer_session(42, "secret")
        self.assertEqual(
            read_reviewer_session(token, "secret"),
            42,
        )
        self.assertIsNone(read_reviewer_session(token + "x", "secret"))

    def test_completion_date_is_set_automatically(self) -> None:
        reviewer, review_date = resolve_review_metadata(
            " Эксперт ",
            complete=True,
            today=date(2026, 6, 9),
        )
        self.assertEqual(reviewer, "Эксперт")
        self.assertEqual(review_date, "2026-06-09")

    def test_export_csv_contains_thesis_fields_and_status(self) -> None:
        submission, errors = validate_review_submission(
            {
                "page_usable": "yes",
                "usability_score": "5",
                "pitch_problem": "1",
                "chord_problem": "1",
            },
            complete=True,
            reviewer="Эксперт",
            review_date="2026-06-09",
        )
        self.assertEqual(errors, [])
        save_review(
            self.db_path,
            1,
            int(self.reviewer_a["id"]),
            submission.as_dict(),
            "completed",
        )

        rows = list(csv.DictReader(io.StringIO(build_export_csv(self.db_path))))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["doc_id"], "rsl01000000001")
        self.assertEqual(rows[0]["reviewer"], "Алексей")
        self.assertEqual(
            rows[0]["reviewer_id"],
            str(self.reviewer_a["id"]),
        )
        self.assertEqual(rows[0]["review_status"], "completed")
        self.assertEqual(rows[0]["page_usable"], "yes")
        self.assertIn("requires_new_omr", rows[0])
        self.assertIn("updated_at", rows[0])
        self.assertEqual(rows[0]["usability_score"], "5")
        self.assertEqual(rows[0]["pitch_problem"], "1")
        self.assertEqual(rows[0]["chord_problem"], "1")
        self.assertIn("unreadable_or_failed", rows[0])
        self.assertNotIn("access_token", rows[0])

    def test_reviewer_is_created_on_first_login_name(self) -> None:
        reviewer, created = get_or_create_reviewer(
            self.db_path,
            "Новый Эксперт",
        )
        self.assertTrue(created)
        self.assertEqual(reviewer["name"], "Новый Эксперт")
        self.assertEqual(reviewer["normalized_name"], "новый эксперт")

    def test_same_normalized_name_reuses_reviewer(self) -> None:
        first, first_created = get_or_create_reviewer(
            self.db_path,
            "Иван Петров",
        )
        second, second_created = get_or_create_reviewer(
            self.db_path,
            "  иВАН   пЕтРов ",
        )
        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first["id"], second["id"])

    def test_previous_reviewer_table_is_migrated(self) -> None:
        legacy_db = self.root / "legacy-reviewers.db"
        with closing(connect(legacy_db)) as connection:
            connection.execute(
                """
                CREATE TABLE reviewers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    access_token TEXT UNIQUE,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                "INSERT INTO reviewers (name) VALUES (?)",
                ("  ИВАН   Петров ",),
            )
            connection.commit()

        init_db(legacy_db)
        reviewer, created = get_or_create_reviewer(
            legacy_db,
            "иван петров",
        )

        self.assertFalse(created)
        self.assertEqual(reviewer["normalized_name"], "иван петров")
        self.assertTrue(reviewer["updated_at"])

    def test_two_reviewers_review_same_item_independently(self) -> None:
        submission_a, errors_a = validate_review_submission(
            {"page_usable": "yes", "usability_score": "5"},
            complete=True,
            reviewer="Алексей",
            review_date="2026-06-09",
        )
        submission_b, errors_b = validate_review_submission(
            {"page_usable": "no", "usability_score": "1"},
            complete=False,
            reviewer="Мария",
        )
        self.assertEqual(errors_a + errors_b, [])

        save_review(
            self.db_path,
            1,
            int(self.reviewer_a["id"]),
            submission_a.as_dict(),
            "completed",
        )
        save_review(
            self.db_path,
            1,
            int(self.reviewer_b["id"]),
            submission_b.as_dict(),
            "draft",
        )

        review_a = get_review(
            self.db_path,
            1,
            int(self.reviewer_a["id"]),
        )
        review_b = get_review(
            self.db_path,
            1,
            int(self.reviewer_b["id"]),
        )
        self.assertEqual(review_a["review_status"], "completed")
        self.assertEqual(review_a["page_usable"], "yes")
        self.assertEqual(review_b["review_status"], "draft")
        self.assertEqual(review_b["page_usable"], "no")

        item_for_a = list_items(
            self.db_path,
            int(self.reviewer_a["id"]),
        )[0]
        item_for_b = list_items(
            self.db_path,
            int(self.reviewer_b["id"]),
        )[0]
        self.assertEqual(item_for_a["review_status"], "completed")
        self.assertEqual(item_for_b["review_status"], "draft")

    def test_export_has_two_rows_for_same_page(self) -> None:
        for reviewer, usable in (
            (self.reviewer_a, "yes"),
            (self.reviewer_b, "partial"),
        ):
            submission, errors = validate_review_submission(
                {"page_usable": usable},
                complete=True,
                reviewer=str(reviewer["name"]),
                review_date="2026-06-09",
            )
            self.assertEqual(errors, [])
            save_review(
                self.db_path,
                1,
                int(reviewer["id"]),
                submission.as_dict(),
                "completed",
            )

        rows = list(csv.DictReader(io.StringIO(build_export_csv(self.db_path))))
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["page_index"] for row in rows}, {"1"})
        self.assertEqual(
            {row["reviewer"] for row in rows},
            {"Алексей", "Мария"},
        )

    def test_cannot_save_without_authorized_reviewer(self) -> None:
        submission, _ = validate_review_submission(
            {"page_usable": "yes"},
            complete=True,
            reviewer="Подмена",
            review_date="2026-06-09",
        )
        with self.assertRaises(PermissionError):
            save_review(
                self.db_path,
                1,
                999999,
                submission.as_dict(),
                "completed",
            )

    def test_master_password_uses_local_reviewer(self) -> None:
        local = get_or_create_local_reviewer(self.db_path)
        self.assertEqual(local["name"], "local")
        self.assertIsNone(local["access_token"])

    def test_legacy_review_is_migrated_to_local_reviewer(self) -> None:
        with closing(connect(self.db_path)) as connection:
            connection.execute(
                """
                UPDATE review_items
                SET review_status = 'completed',
                    reviewer = 'Старый эксперт',
                    review_date = '2026-06-01',
                    page_usable = 'partial',
                    updated_at = '2026-06-01 12:00:00'
                WHERE item_number = 2
                """
            )
            connection.commit()

        init_db(self.db_path)
        local = get_or_create_local_reviewer(self.db_path)
        migrated = get_review(self.db_path, 2, int(local["id"]))

        self.assertIsNotNone(migrated)
        self.assertEqual(migrated["review_status"], "completed")
        self.assertEqual(migrated["page_usable"], "partial")
        untouched_for_a = get_item(
            self.db_path,
            2,
            int(self.reviewer_a["id"]),
        )
        self.assertEqual(untouched_for_a["review_status"], "not_reviewed")
        self.assertEqual(untouched_for_a["page_usable"], "")


@unittest.skipUnless(
    WEB_TESTS_AVAILABLE,
    "FastAPI/httpx/Jinja2 are not installed in this runtime",
)
class ReviewAppHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        from fastapi.testclient import TestClient
        from review_app.main import create_app

        self.temporary_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_dir.name)
        self.package_dir = self.root / "package"
        self.db_path = self.root / "review.db"
        create_package(self.package_dir)
        import_package(self.package_dir, self.db_path)
        self.client = TestClient(
            create_app(
                db_path=self.db_path,
                package_dir=self.package_dir,
                password="test-secret",
            )
        )

    def tearDown(self) -> None:
        self.client.close()
        self.temporary_dir.cleanup()

    def login(self) -> None:
        response = self.client.post(
            "/login",
            data={
                "password": "test-secret",
                "reviewer_name": "Эксперт из формы",
                "next": "/",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        self.reviewer, _ = get_or_create_reviewer(
            self.db_path,
            "Эксперт из формы",
        )

    def test_protected_pages_require_login(self) -> None:
        response = self.client.get("/", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers["location"].startswith("/login"))

    def test_http_draft_and_complete_review(self) -> None:
        self.login()
        draft = self.client.post(
            "/review/1",
            data={
                "action": "draft",
                "page_usable": "partial",
                "usability_score": "3",
            },
            follow_redirects=False,
        )
        self.assertEqual(draft.status_code, 303)
        self.assertEqual(
            get_item(
                self.db_path,
                1,
                int(self.reviewer["id"]),
            )["review_status"],
            "draft",
        )

        complete = self.client.post(
            "/review/1",
            data={
                "action": "complete",
                "page_usable": "yes",
                "usability_score": "5",
                "pitch_problem": "1",
            },
            follow_redirects=False,
        )
        self.assertEqual(complete.status_code, 303)
        self.assertEqual(
            get_item(
                self.db_path,
                1,
                int(self.reviewer["id"]),
            )["review_status"],
            "completed",
        )
        item = get_item(
            self.db_path,
            1,
            int(self.reviewer["id"]),
        )
        self.assertEqual(item["reviewer"], "Эксперт из формы")
        self.assertEqual(item["review_date"], date.today().isoformat())
        self.assertEqual(item["checked_measures"], 0)

    def test_export_and_media_are_protected(self) -> None:
        unauthenticated = self.client.get(
            "/export/expert_review.csv",
            follow_redirects=False,
        )
        self.assertEqual(unauthenticated.status_code, 303)

        self.login()
        page = self.client.get("/review/1")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(str(self.package_dir), page.text)
        media = self.client.get("/media/1/scan")
        self.assertEqual(media.status_code, 200)
        self.assertEqual(media.content, b"png")
        self.assertEqual(media.headers["content-type"], "image/png")
        self.assertEqual(
            media.headers["cache-control"],
            "public, max-age=3600",
        )
        self.assertEqual(media.headers["accept-ranges"], "bytes")
        audio = self.client.get("/media/1/audio")
        self.assertEqual(audio.status_code, 200)
        self.assertEqual(audio.headers["content-type"], "audio/mpeg")
        missing = self.client.get("/media/999/audio")
        self.assertEqual(missing.status_code, 404)
        export = self.client.get("/export/expert_review.csv")
        self.assertEqual(export.status_code, 200)

    def test_common_password_login_requires_name(self) -> None:
        missing_name = self.client.post(
            "/login",
            data={"password": "test-secret", "reviewer_name": "", "next": "/"},
            follow_redirects=False,
        )
        self.assertEqual(missing_name.status_code, 422)

        response = self.client.post(
            "/login",
            data={
                "password": "test-secret",
                "reviewer_name": "Локальный эксперт",
                "next": "/",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)


if __name__ == "__main__":
    unittest.main()
