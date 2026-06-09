"""Tests for read-only document dashboard aggregation."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from review_app.dashboard import (
    available_reports,
    dashboard_audio_path,
    dashboard_artifact_path,
    load_dashboard_data,
    load_inbox_overview,
    load_page_detail,
)
from review_app.database import get_or_create_reviewer
from review_app.import_package import import_package


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def create_dashboard_fixture(root: Path) -> None:
    write_csv(
        root / "data" / "labels" / "document_inventory.csv",
        [
            {
                "doc_id": "rsl001",
                "title": "Test score",
                "authors": "Composer",
                "year": "1900",
                "language": "rus",
                "publication": "Moscow",
                "record_id": "1",
                "pages_count": "2",
                "pdf_status": "exists",
                "mrc_status": "parsed",
            }
        ],
    )
    write_csv(
        root / "data" / "labels" / "pages_validated_thesis.csv",
        [
            {
                "doc_id": "rsl001",
                "page_index": "1",
                "page_type": "music",
                "has_music": "1",
                "image_path": "outputs/pages/rsl001/page_001.png",
                "validation_source": "manual_thesis",
            },
            {
                "doc_id": "rsl001",
                "page_index": "2",
                "page_type": "title",
                "has_music": "0",
                "image_path": "outputs/pages/rsl001/page_002.png",
                "validation_source": "manual_thesis",
            },
        ],
    )


class DocumentDashboardTests(unittest.TestCase):
    def test_dashboard_handles_missing_optional_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            create_dashboard_fixture(root)

            dashboard = load_dashboard_data(root)

            document = dashboard["documents"][0]
            self.assertEqual(document["doc_id"], "rsl001")
            self.assertEqual(document["music_pages_count"], 1)
            self.assertEqual(document["page_type_counts"]["music"], 1)
            self.assertEqual(document["omr_success_count"], 0)
            pages = dashboard["pages_by_doc"]["rsl001"]
            self.assertEqual(pages[0]["omr_status"], "not_run")
            self.assertEqual(pages[0]["music_features"]["source"], "unknown")

    def test_dashboard_detects_artifacts_and_features(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            create_dashboard_fixture(root)
            mxl = (
                root
                / "outputs"
                / "omr_300dpi"
                / "rsl001"
                / "page_001"
                / "page_001.mxl"
            )
            midi = root / "outputs" / "midi" / "rsl001" / "page_001.mid"
            image = root / "outputs" / "pages" / "rsl001" / "page_001.png"
            for path, content in ((mxl, b"mxl"), (midi, b"mid"), (image, b"png")):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            write_csv(
                root / "outputs" / "reports" / "music_features.csv",
                [
                    {
                        "doc_id": "rsl001",
                        "page_index": "1",
                        "key_name_ru": "до мажор",
                        "key_name_latin": "C major",
                        "key_signature_name_ru": "до мажор / ля минор",
                        "key_signature_name_latin": "C-dur / a-moll",
                        "detected_tonality_ru": "до мажор",
                        "detected_tonality_latin": "C-dur",
                        "mode_status": "detected",
                        "time_signature": "4/4",
                        "clefs": "treble",
                        "instruments": "piano",
                        "confidence": "high",
                        "source": "musicxml",
                    }
                ],
            )

            dashboard = load_dashboard_data(root)
            page = dashboard["pages_by_doc"]["rsl001"][0]

            self.assertTrue(page["has_image"])
            self.assertTrue(page["has_mxl"])
            self.assertTrue(page["has_midi"])
            self.assertEqual(page["omr_status"], "omr_success")
            self.assertEqual(page["music_features"]["time_signature"], "4/4")
            self.assertEqual(
                dashboard_artifact_path(root, "rsl001", 1, "mxl"),
                mxl.resolve(),
            )

    def test_inbox_and_reports_can_be_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.assertEqual(load_inbox_overview(root)["files"], [])
            self.assertEqual(available_reports(root), [])

    def test_fallback_recovery_is_visible_and_downloadable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            create_dashboard_fixture(root)
            fallback_mxl = (
                root
                / "outputs"
                / "omr_400dpi_fallback"
                / "rsl001"
                / "page_001"
                / "page_001.mxl"
            )
            fallback_mxl.parent.mkdir(parents=True)
            fallback_mxl.write_bytes(b"mxl")
            write_csv(
                root
                / "outputs"
                / "reports"
                / "omr_400dpi_fallback_report.csv",
                [
                    {
                        "doc_id": "rsl001",
                        "page_index": "1",
                        "primary_failure_status": "missing_mxl",
                        "fallback_400_status": "recovered",
                        "fallback_400_mxl_path": str(
                            fallback_mxl.relative_to(root)
                        ),
                        "fallback_400_midi_path": "",
                    }
                ],
            )

            dashboard = load_dashboard_data(root)
            page = dashboard["pages_by_doc"]["rsl001"][0]

            self.assertEqual(page["omr_status"], "fallback_recovered")
            self.assertTrue(page["has_mxl"])
            self.assertEqual(
                dashboard_artifact_path(root, "rsl001", 1, "mxl"),
                fallback_mxl.resolve(),
            )

    def test_page_detail_collects_review_audio_and_tracks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            create_dashboard_fixture(root)
            package = root / "package"
            package.mkdir()
            prefix = "01_rsl001_page_001"
            (package / f"{prefix}_scan.png").write_bytes(b"scan")
            audio = package / f"{prefix}_audio.mp3"
            track = package / f"{prefix}_track_01.mp3"
            audio.write_bytes(b"audio")
            track.write_bytes(b"track")
            db_path = root / "review.db"
            import_package(package, db_path)
            reviewer, _ = get_or_create_reviewer(db_path, "Expert")

            detail = load_page_detail(
                root,
                db_path,
                package,
                "rsl001",
                1,
                int(reviewer["id"]),
            )

            self.assertIsNotNone(detail)
            self.assertTrue(detail["has_audio"])
            self.assertEqual(detail["tracks_count"], 1)
            self.assertEqual(detail["review_item"]["item_number"], 1)
            self.assertEqual(
                dashboard_audio_path(
                    root, db_path, package, "rsl001", 1
                ),
                audio.resolve(),
            )
            self.assertEqual(
                dashboard_audio_path(
                    root, db_path, package, "rsl001", 1, 1
                ),
                track.resolve(),
            )

    def test_page_detail_is_robust_without_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            create_dashboard_fixture(root)
            package = root / "empty-package"
            package.mkdir()
            db_path = root / "review.db"

            detail = load_page_detail(
                root, db_path, package, "rsl001", 2
            )

            self.assertIsNotNone(detail)
            self.assertFalse(detail["page"]["has_mxl"])
            self.assertFalse(detail["page"]["has_midi"])
            self.assertFalse(detail["has_audio"])
            self.assertEqual(detail["tracks_count"], 0)
            self.assertIsNone(
                load_page_detail(root, db_path, package, "rsl001", 99)
            )


if __name__ == "__main__":
    unittest.main()
