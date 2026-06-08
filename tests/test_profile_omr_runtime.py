"""Tests for OMR runtime profiling."""

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "profile_omr_runtime.py"
SPEC = importlib.util.spec_from_file_location("profile_omr_runtime", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
profile = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(profile)


def write_native_log(path: Path, start: str, end: str) -> None:
    """Write a minimal Audiveris-native log with two timestamps."""
    path.write_text(
        "\n".join(
            [
                f"{start} INFO [] Main | start",
                f"{end} INFO [] Main | end",
            ]
        ),
        encoding="utf-8",
    )


class ProfileOmrRuntimeTests(unittest.TestCase):
    def test_collects_and_summarizes_success_and_failed_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            report_rows = []
            definitions = [
                ("doc-a", 1, "success", "00:00:00,000", "00:00:10,000"),
                ("doc-a", 2, "success", "00:00:00,000", "00:00:20,000"),
                ("doc-b", 1, "failed", "00:00:00,000", "00:00:05,000"),
            ]
            for doc_id, page_index, status, start, end in definitions:
                output_dir = root / doc_id / f"page_{page_index:03d}"
                output_dir.mkdir(parents=True)
                write_native_log(
                    output_dir / f"page_{page_index:03d}-run.log",
                    f"2026-06-08 {start}",
                    f"2026-06-08 {end}",
                )
                report_rows.append(
                    {
                        "doc_id": doc_id,
                        "page_index": str(page_index),
                        "output_dir": str(output_dir),
                        "status": status,
                    }
                )

            measurements = profile.collect_runtime_measurements(report_rows)
            summaries = profile.summarize_runtimes(measurements)

            success = summaries[0]
            failed = summaries[1]
            self.assertEqual(success["pages"], 2)
            self.assertEqual(success["mean_seconds"], 15.0)
            self.assertEqual(success["median_seconds"], 15.0)
            self.assertEqual(success["p90_seconds"], 19.0)
            self.assertEqual(success["p95_seconds"], 19.5)
            self.assertEqual(success["fastest_page_index"], 1)
            self.assertEqual(success["slowest_page_index"], 2)
            self.assertEqual(failed["pages"], 1)
            self.assertEqual(failed["mean_seconds"], 5.0)

    def test_missing_log_is_reported_without_stopping(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            rows = [
                {
                    "doc_id": "doc-a",
                    "page_index": "1",
                    "output_dir": str(Path(temporary_dir) / "missing"),
                    "status": "failed",
                }
            ]

            measurements = profile.collect_runtime_measurements(rows)

            self.assertEqual(
                measurements[0]["measurement_status"],
                "missing_log",
            )
            self.assertEqual(measurements[0]["duration_seconds"], "")

    def test_calculates_eligible_pages_per_document(self) -> None:
        labels = [
            {"doc_id": "a", "page_type": "music", "has_music": "1"},
            {"doc_id": "a", "page_type": "mixed", "has_music": "1"},
            {"doc_id": "a", "page_type": "text", "has_music": "0"},
            {"doc_id": "b", "page_type": "music", "has_music": "1"},
            {"doc_id": "b", "page_type": "unknown", "has_music": "1"},
        ]

        pages_per_document = profile.calculate_pages_per_document(labels)

        self.assertEqual(pages_per_document, 1.5)

    def test_scale_estimates_apply_worker_count(self) -> None:
        estimates = profile.build_scale_estimates(
            mean_seconds_per_page=10,
            pages_per_document=2,
            document_scales=(100,),
            worker_counts=(1, 2, 4),
        )

        self.assertEqual([row["estimated_pages"] for row in estimates], [200] * 3)
        self.assertEqual(
            [row["estimated_seconds"] for row in estimates],
            [2000.0, 1000.0, 500.0],
        )

    def test_writes_expected_csv_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output_path = Path(temporary_dir) / "summary.csv"
            profile.write_csv(
                output_path,
                [{"status": "success", "pages": 1}],
                ["status", "pages"],
            )

            with output_path.open(
                "r",
                encoding="utf-8",
                newline="",
            ) as source:
                reader = csv.DictReader(source)
                self.assertEqual(reader.fieldnames, ["status", "pages"])
                self.assertEqual(next(reader)["status"], "success")


if __name__ == "__main__":
    unittest.main()
