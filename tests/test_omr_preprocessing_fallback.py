"""Tests for the experimental preprocessing OMR fallback."""

import csv
import tempfile
import unittest
from pathlib import Path

from scripts.run_omr_preprocessing_fallback import (
    VARIANTS,
    run_preprocessing_fallback,
    select_preprocessing_failures,
    summarize_preprocessing_fallback,
)


class OmrPreprocessingFallbackTests(unittest.TestCase):
    def test_selects_only_pages_still_failed_at_400dpi(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = Path(temp_dir) / "fallback.csv"
            with report.open("w", encoding="utf-8", newline="") as csv_file:
                writer = csv.DictWriter(
                    csv_file,
                    fieldnames=(
                        "doc_id",
                        "page_index",
                        "fallback_400_status",
                    ),
                )
                writer.writeheader()
                writer.writerows(
                    [
                        {
                            "doc_id": "rsl001",
                            "page_index": 1,
                            "fallback_400_status": "still_failed",
                        },
                        {
                            "doc_id": "rsl001",
                            "page_index": 2,
                            "fallback_400_status": "recovered_midi",
                        },
                    ]
                )

            pages = select_preprocessing_failures(report)

            self.assertEqual(pages, [{"doc_id": "rsl001", "page_index": 1}])

    def test_runs_all_variants_and_records_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "pages" / "rsl001" / "page_001.png"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"source")

            def preparer(source_path, destination):
                destination.mkdir(parents=True)
                result = {}
                for variant in VARIANTS:
                    path = destination / f"{variant}.png"
                    path.write_bytes(b"image")
                    result[variant] = path
                return result

            def audiveris(input_path, output_dir, **kwargs):
                if input_path.stem == "crop_deskew_clahe":
                    output_dir.mkdir(parents=True, exist_ok=True)
                    (output_dir / "page_001.mxl").write_bytes(b"mxl")
                    return {"status": "success", "message": ""}
                return {"status": "failed", "message": "no staff"}

            def midi(source_mxl, midi_path):
                midi_path.parent.mkdir(parents=True, exist_ok=True)
                midi_path.write_bytes(b"midi")
                return {
                    "status": "success",
                    "message": "",
                    "midi_path": str(midi_path),
                }

            ticks = iter(float(value) for value in range(8))
            rows = run_preprocessing_fallback(
                [{"doc_id": "rsl001", "page_index": 1}],
                pages_dir=root / "pages",
                out_dir=root / "omr",
                midi_dir=root / "midi",
                variant_preparer=preparer,
                audiveris_runner=audiveris,
                midi_converter=midi,
                clock=lambda: next(ticks),
            )

            self.assertEqual([row["variant"] for row in rows], list(VARIANTS))
            recovered = [
                row
                for row in rows
                if row["preprocessing_fallback_status"] == "recovered_midi"
            ]
            self.assertEqual(len(recovered), 1)
            self.assertEqual(recovered[0]["variant"], "crop_deskew_clahe")

            summary = summarize_preprocessing_fallback(rows)
            self.assertEqual(summary["pages_attempted"], 1)
            self.assertEqual(summary["recovered_pages"], 1)
            self.assertEqual(
                summary["best_variants"][("rsl001", 1)],
                "crop_deskew_clahe",
            )

    def test_resume_skips_existing_variant_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "pages" / "rsl001" / "page_001.png"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"source")

            def preparer(source_path, destination):
                destination.mkdir(parents=True)
                paths = {}
                for variant in VARIANTS:
                    path = destination / f"{variant}.png"
                    path.write_bytes(b"image")
                    paths[variant] = path
                    output = root / "omr" / "rsl001" / "page_001" / variant
                    output.mkdir(parents=True, exist_ok=True)
                    (output / "page_001.mxl").write_bytes(b"mxl")
                    midi = root / "midi" / "rsl001" / "page_001" / f"{variant}.mid"
                    midi.parent.mkdir(parents=True, exist_ok=True)
                    midi.write_bytes(b"midi")
                return paths

            calls = []
            rows = run_preprocessing_fallback(
                [{"doc_id": "rsl001", "page_index": 1}],
                pages_dir=root / "pages",
                out_dir=root / "omr",
                midi_dir=root / "midi",
                resume=True,
                variant_preparer=preparer,
                audiveris_runner=lambda *args, **kwargs: calls.append("omr"),
                midi_converter=lambda *args: calls.append("midi"),
            )

            self.assertEqual(calls, [])
            self.assertTrue(all(row["run_action"] == "skipped" for row in rows))
            self.assertTrue(
                all(
                    row["preprocessing_fallback_status"] == "recovered_midi"
                    for row in rows
                )
            )


if __name__ == "__main__":
    unittest.main()
