"""Tests for the isolated 400 DPI OMR fallback experiment."""

import csv
import tempfile
import unittest
from pathlib import Path

from scripts.run_omr_fallback_dpi import (
    calculate_fallback_summary,
    run_fallback_pages,
    select_failed_pages,
)


class OmrFallbackDpiTests(unittest.TestCase):
    def test_selects_missing_mxl_pages_from_aggregate_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            aggregate = root / "omr_pipeline_report.csv"
            failures = root / "omr_failure_report.csv"
            with aggregate.open("w", encoding="utf-8", newline="") as csv_file:
                writer = csv.DictWriter(
                    csv_file,
                    fieldnames=("doc_id", "sampled_pages", "mxl_generated_pages"),
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "doc_id": "rsl001",
                        "sampled_pages": 10,
                        "mxl_generated_pages": 8,
                    }
                )
            with failures.open("w", encoding="utf-8", newline="") as csv_file:
                writer = csv.DictWriter(
                    csv_file,
                    fieldnames=(
                        "doc_id",
                        "page_index",
                        "has_mxl",
                        "failure_type",
                    ),
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "doc_id": "rsl001",
                        "page_index": 3,
                        "has_mxl": "False",
                        "failure_type": "missing_mxl",
                    }
                )
                writer.writerow(
                    {
                        "doc_id": "rsl001",
                        "page_index": 4,
                        "has_mxl": "True",
                        "failure_type": "missing_midi",
                    }
                )

            pages, context = select_failed_pages(aggregate)

            self.assertEqual([(row["doc_id"], row["page_index"]) for row in pages], [("rsl001", 3)])
            self.assertEqual(context["sample_total"], 10)
            self.assertEqual(context["total_300dpi_failures"], 2)

    def test_skip_existing_does_not_run_audiveris(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            page_dir = root / "omr" / "rsl001" / "page_003"
            midi_path = root / "midi" / "rsl001" / "page_003.mid"
            page_dir.mkdir(parents=True)
            midi_path.parent.mkdir(parents=True)
            (page_dir / "page_003.mxl").write_bytes(b"mxl")
            midi_path.write_bytes(b"midi")
            calls = []

            rows = run_fallback_pages(
                [
                    {
                        "doc_id": "rsl001",
                        "page_index": 3,
                        "primary_failure_status": "missing_mxl",
                    }
                ],
                raw_dir=root / "raw",
                pages_dir=root / "pages",
                out_dir=root / "omr",
                midi_dir=root / "midi",
                skip_existing=True,
                extractor=lambda *args: calls.append("extract"),
                audiveris_runner=lambda *args, **kwargs: calls.append("omr"),
                midi_converter=lambda *args: calls.append("midi"),
            )

            self.assertEqual(calls, [])
            self.assertEqual(rows[0]["run_action"], "skipped")
            self.assertEqual(rows[0]["fallback_400_status"], "recovered_midi")

    def test_runs_full_recovery_and_records_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            def extractor(raw_dir, doc_id, page_index, output_path, dpi):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"png")
                self.assertEqual(dpi, 400)

            def audiveris(input_path, output_dir, **kwargs):
                (output_dir / "page_003.mxl").write_bytes(b"mxl")
                return {"status": "success", "message": ""}

            def midi(source_mxl, midi_path):
                midi_path.parent.mkdir(parents=True, exist_ok=True)
                midi_path.write_bytes(b"midi")
                return {
                    "status": "success",
                    "message": "",
                    "midi_path": str(midi_path),
                }

            ticks = iter((10.0, 12.5))
            rows = run_fallback_pages(
                [
                    {
                        "doc_id": "rsl001",
                        "page_index": 3,
                        "primary_failure_status": "missing_mxl",
                    }
                ],
                raw_dir=root / "raw",
                pages_dir=root / "pages",
                out_dir=root / "omr",
                midi_dir=root / "midi",
                extractor=extractor,
                audiveris_runner=audiveris,
                midi_converter=midi,
                clock=lambda: next(ticks),
            )

            self.assertEqual(rows[0]["fallback_400_status"], "recovered_midi")
            self.assertEqual(rows[0]["fallback_400_runtime_seconds"], 2.5)
            self.assertTrue(rows[0]["fallback_400_mxl_path"])
            self.assertTrue(rows[0]["fallback_400_midi_path"])

    def test_recovery_and_combined_success_rates(self) -> None:
        summary = calculate_fallback_summary(
            [
                {
                    "fallback_400_status": "recovered_midi",
                    "fallback_400_runtime_seconds": 2.0,
                },
                {
                    "fallback_400_status": "still_failed",
                    "fallback_400_runtime_seconds": 3.0,
                },
            ],
            total_300dpi_failures=9,
            sample_total=150,
        )

        self.assertEqual(summary["recovered_mxl"], 1)
        self.assertEqual(summary["still_failed"], 1)
        self.assertEqual(summary["fallback_recovery_rate"], 0.5)
        self.assertAlmostEqual(summary["combined_success_rate"], 142 / 150)
        self.assertEqual(summary["fallback_runtime_seconds"], 5.0)


if __name__ == "__main__":
    unittest.main()
