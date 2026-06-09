"""Tests for the protected OMR failure review workflow."""

import csv
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

from review_app.database import (
    get_failure_review,
    list_failure_reviews,
    save_failure_review,
)
from review_app.export_failures import build_failure_export_csv
from review_app.failure_schemas import validate_failure_submission
from review_app.import_failures import discover_failure_items, import_failures


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


def create_failure_source(root: Path) -> tuple[Path, Path, Path]:
    pages_dir = root / "outputs" / "pages"
    omr_dir = root / "outputs" / "omr_300dpi"
    report_path = root / "outputs" / "reports" / "omr_failure_report.csv"
    labels_path = root / "data" / "labels" / "pages_validated_thesis.csv"
    page_path = pages_dir / "rsl001" / "page_003.png"
    log_path = omr_dir / "rsl001" / "page_003" / "page_003_audiveris.log"
    page_path.parent.mkdir(parents=True)
    log_path.parent.mkdir(parents=True)
    report_path.parent.mkdir(parents=True)
    labels_path.parent.mkdir(parents=True)
    page_path.write_bytes(b"scan")
    log_path.write_text("INFO start\nERROR small interline\n", encoding="utf-8")
    with report_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=(
                "doc_id",
                "page_index",
                "image_path",
                "has_mxl",
                "has_midi",
                "failure_type",
            ),
        )
        writer.writeheader()
        writer.writerow(
            {
                "doc_id": "rsl001",
                "page_index": 3,
                "image_path": "outputs/pages/rsl001/page_003.png",
                "has_mxl": "False",
                "has_midi": "False",
                "failure_type": "missing_mxl",
            }
        )
        writer.writerow(
            {
                "doc_id": "rsl001",
                "page_index": 4,
                "image_path": "outputs/pages/rsl001/page_004.png",
                "has_mxl": "True",
                "has_midi": "True",
                "failure_type": "",
            }
        )
    with labels_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=("doc_id", "page_index", "page_type"),
        )
        writer.writeheader()
        writer.writerow(
            {"doc_id": "rsl001", "page_index": 3, "page_type": "mixed"}
        )
    return report_path, labels_path, omr_dir


class FailureReviewCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_dir.name)
        self.db_path = self.root / "review.db"
        self.report_path, self.labels_path, self.omr_dir = create_failure_source(
            self.root
        )

    def tearDown(self) -> None:
        self.temporary_dir.cleanup()

    def import_source(self) -> int:
        return import_failures(
            self.report_path,
            self.db_path,
            project_root=self.root,
            labels_path=self.labels_path,
            pages_dir=self.root / "outputs" / "pages",
            omr_dir=self.omr_dir,
        )

    def test_import_failures_finds_page_type_scan_and_log(self) -> None:
        items = discover_failure_items(
            self.report_path,
            project_root=self.root,
            labels_path=self.labels_path,
            pages_dir=self.root / "outputs" / "pages",
            omr_dir=self.omr_dir,
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["page_type"], "mixed")
        self.assertEqual(items[0]["failure_status"], "missing_mxl")
        self.assertEqual(items[0]["image_path"], "outputs/pages/rsl001/page_003.png")
        self.assertIn("small interline", items[0]["audiveris_log_excerpt"])

        self.assertEqual(self.import_source(), 1)
        stored = list_failure_reviews(self.db_path)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["failure_reason"], "unknown_failure")

    def test_save_draft_and_mark_reviewed(self) -> None:
        self.import_source()
        failure = list_failure_reviews(self.db_path)[0]
        draft, errors = validate_failure_submission(
            {
                "failure_reason": "small_interline",
                "decision": "",
                "image_quality_issue": "low resolution",
                "audiveris_log_excerpt": "interline",
                "expert_comment": "Retry at higher DPI",
            },
            reviewed=False,
        )
        self.assertEqual(errors, [])
        save_failure_review(
            self.db_path,
            int(failure["id"]),
            draft,
            "Researcher",
            "draft",
        )
        stored = get_failure_review(self.db_path, int(failure["id"]))
        self.assertEqual(stored["review_status"], "draft")
        self.assertEqual(stored["failure_reason"], "small_interline")

        reviewed, errors = validate_failure_submission(
            {**draft, "decision": "retry_preprocessed"},
            reviewed=True,
        )
        self.assertEqual(errors, [])
        save_failure_review(
            self.db_path,
            int(failure["id"]),
            reviewed,
            "Researcher",
            "reviewed",
        )
        stored = get_failure_review(self.db_path, int(failure["id"]))
        self.assertEqual(stored["review_status"], "reviewed")
        self.assertEqual(stored["decision"], "retry_preprocessed")
        self.assertTrue(stored["updated_at"])

    def test_reimport_does_not_overwrite_manual_classification(self) -> None:
        self.import_source()
        failure = list_failure_reviews(self.db_path)[0]
        values, _ = validate_failure_submission(
            {
                "failure_reason": "cropped",
                "decision": "exclude_from_omr",
                "audiveris_log_excerpt": "manual excerpt",
            },
            reviewed=True,
        )
        save_failure_review(
            self.db_path,
            int(failure["id"]),
            values,
            "Researcher",
            "reviewed",
        )

        self.import_source()

        stored = get_failure_review(self.db_path, int(failure["id"]))
        self.assertEqual(stored["failure_reason"], "cropped")
        self.assertEqual(stored["review_status"], "reviewed")
        self.assertEqual(stored["audiveris_log_excerpt"], "manual excerpt")

    def test_export_csv_has_thesis_compatible_fields(self) -> None:
        self.import_source()
        rows = list(
            csv.DictReader(io.StringIO(build_failure_export_csv(self.db_path)))
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["doc_id"], "rsl001")
        self.assertEqual(rows[0]["page_index"], "3")
        self.assertIn("failure_reason", rows[0])
        self.assertIn("decision", rows[0])
        self.assertIn("fallback_400_status", rows[0])
        self.assertIn("fallback_400_mxl_path", rows[0])
        self.assertIn("fallback_400_midi_path", rows[0])
        self.assertIn("fallback_400_runtime_seconds", rows[0])
        self.assertIn("fallback_400_error", rows[0])
        self.assertIn("preprocessing_fallback_status", rows[0])
        self.assertIn("preprocessing_best_variant", rows[0])
        self.assertIn("preprocessing_mxl_path", rows[0])
        self.assertIn("preprocessing_midi_path", rows[0])
        self.assertIn("preprocessing_runtime_seconds", rows[0])
        self.assertIn("preprocessing_error", rows[0])
        self.assertNotIn("image_path", rows[0])
        self.assertNotIn("log_path", rows[0])

    def test_import_and_export_include_400dpi_fallback_fields(self) -> None:
        fallback_report = self.root / "outputs" / "reports" / (
            "omr_400dpi_fallback_report.csv"
        )
        with fallback_report.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=(
                    "doc_id",
                    "page_index",
                    "fallback_400_status",
                    "fallback_400_mxl_path",
                    "fallback_400_midi_path",
                    "fallback_400_runtime_seconds",
                    "fallback_400_error",
                ),
            )
            writer.writeheader()
            writer.writerow(
                {
                    "doc_id": "rsl001",
                    "page_index": 3,
                    "fallback_400_status": "recovered_midi",
                    "fallback_400_mxl_path": (
                        "outputs/omr_400dpi_fallback/rsl001/page_003/page_003.mxl"
                    ),
                    "fallback_400_midi_path": (
                        "outputs/midi_400dpi_fallback/rsl001/page_003.mid"
                    ),
                    "fallback_400_runtime_seconds": "12.5",
                    "fallback_400_error": "",
                }
            )

        import_failures(
            self.report_path,
            self.db_path,
            project_root=self.root,
            labels_path=self.labels_path,
            pages_dir=self.root / "outputs" / "pages",
            omr_dir=self.omr_dir,
            fallback_report=fallback_report,
        )

        stored = list_failure_reviews(self.db_path)[0]
        self.assertEqual(stored["fallback_400_status"], "recovered_midi")
        self.assertEqual(stored["fallback_400_runtime_seconds"], 12.5)
        exported = list(
            csv.DictReader(io.StringIO(build_failure_export_csv(self.db_path)))
        )[0]
        self.assertEqual(exported["fallback_400_status"], "recovered_midi")
        self.assertEqual(exported["fallback_400_runtime_seconds"], "12.5")

    def test_import_aggregates_preprocessing_fallback_fields(self) -> None:
        preprocessing_report = self.root / "outputs" / "reports" / (
            "omr_preprocessing_fallback_report.csv"
        )
        with preprocessing_report.open(
            "w", encoding="utf-8", newline=""
        ) as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=(
                    "doc_id",
                    "page_index",
                    "variant",
                    "preprocessing_fallback_status",
                    "preprocessing_mxl_path",
                    "preprocessing_midi_path",
                    "preprocessing_runtime_seconds",
                    "preprocessing_error",
                ),
            )
            writer.writeheader()
            writer.writerow(
                {
                    "doc_id": "rsl001",
                    "page_index": 3,
                    "variant": "crop_page",
                    "preprocessing_fallback_status": "still_failed",
                    "preprocessing_mxl_path": "",
                    "preprocessing_midi_path": "",
                    "preprocessing_runtime_seconds": "2.0",
                    "preprocessing_error": "failed",
                }
            )
            writer.writerow(
                {
                    "doc_id": "rsl001",
                    "page_index": 3,
                    "variant": "crop_deskew_clahe",
                    "preprocessing_fallback_status": "recovered_midi",
                    "preprocessing_mxl_path": "result.mxl",
                    "preprocessing_midi_path": "result.mid",
                    "preprocessing_runtime_seconds": "3.5",
                    "preprocessing_error": "",
                }
            )

        import_failures(
            self.report_path,
            self.db_path,
            project_root=self.root,
            labels_path=self.labels_path,
            pages_dir=self.root / "outputs" / "pages",
            omr_dir=self.omr_dir,
            fallback_report=None,
            preprocessing_report=preprocessing_report,
        )

        stored = list_failure_reviews(self.db_path)[0]
        self.assertEqual(
            stored["preprocessing_fallback_status"], "recovered_midi"
        )
        self.assertEqual(
            stored["preprocessing_best_variant"], "crop_deskew_clahe"
        )
        self.assertEqual(stored["preprocessing_runtime_seconds"], 5.5)
        exported = list(
            csv.DictReader(io.StringIO(build_failure_export_csv(self.db_path)))
        )[0]
        self.assertEqual(
            exported["preprocessing_best_variant"], "crop_deskew_clahe"
        )

    def test_reviewed_requires_decision(self) -> None:
        _, errors = validate_failure_submission(
            {"failure_reason": "unknown_failure", "decision": ""},
            reviewed=True,
        )
        self.assertTrue(errors)


@unittest.skipUnless(
    WEB_TESTS_AVAILABLE,
    "FastAPI/httpx/Jinja2 are not installed in this runtime",
)
class FailureReviewHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        from fastapi.testclient import TestClient
        from review_app.main import create_app

        self.temporary_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_dir.name)
        self.db_path = self.root / "review.db"
        report, labels, omr_dir = create_failure_source(self.root)
        import_failures(
            report,
            self.db_path,
            project_root=self.root,
            labels_path=labels,
            pages_dir=self.root / "outputs" / "pages",
            omr_dir=omr_dir,
        )
        self.failure = list_failure_reviews(self.db_path)[0]
        self.client = TestClient(
            create_app(
                db_path=self.db_path,
                package_dir=self.root / "package",
                project_root=self.root,
                password="secret",
            )
        )

    def tearDown(self) -> None:
        self.client.close()
        self.temporary_dir.cleanup()

    def login(self) -> None:
        response = self.client.post(
            "/login",
            data={
                "password": "secret",
                "reviewer_name": "Failure reviewer",
                "next": "/failures",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)

    def test_list_save_review_export_and_protected_files(self) -> None:
        failure_id = int(self.failure["id"])
        for path in (
            "/failures",
            f"/failure-media/{failure_id}/scan",
            f"/failure-media/{failure_id}/log",
            "/export/failure_review.csv",
        ):
            response = self.client.get(path, follow_redirects=False)
            self.assertEqual(response.status_code, 303)

        self.login()
        page = self.client.get("/failures")
        self.assertEqual(page.status_code, 200)
        self.assertIn("rsl001", page.text)
        self.assertNotIn(str(self.root), page.text)

        draft = self.client.post(
            f"/failures/{failure_id}",
            data={
                "action": "draft",
                "failure_reason": "small_interline",
                "decision": "",
            },
            follow_redirects=False,
        )
        self.assertEqual(draft.status_code, 303)
        self.assertEqual(
            get_failure_review(self.db_path, failure_id)["review_status"],
            "draft",
        )

        reviewed = self.client.post(
            f"/failures/{failure_id}",
            data={
                "action": "reviewed",
                "failure_reason": "small_interline",
                "decision": "retry_preprocessed",
            },
            follow_redirects=False,
        )
        self.assertEqual(reviewed.status_code, 303)
        self.assertEqual(
            get_failure_review(self.db_path, failure_id)["review_status"],
            "reviewed",
        )
        self.assertEqual(
            self.client.get(f"/failure-media/{failure_id}/scan").content,
            b"scan",
        )
        self.assertIn(
            b"small interline",
            self.client.get(f"/failure-media/{failure_id}/log").content,
        )
        export = self.client.get("/export/failure_review.csv")
        self.assertEqual(export.status_code, 200)
        self.assertIn("retry_preprocessed", export.text)


if __name__ == "__main__":
    unittest.main()
