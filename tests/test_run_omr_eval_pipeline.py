"""Tests for the one-command OMR evaluation orchestration."""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from run_omr_eval_pipeline import (  # noqa: E402
    build_combined_rows,
    calculate_combined_summary,
    run_omr_eval_pipeline,
)


def _write_sample(path: Path, pages: int = 4) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["doc_id", "page_index", "image_path"],
        )
        writer.writeheader()
        for page_index in range(1, pages + 1):
            writer.writerow(
                {
                    "doc_id": "doc-a",
                    "page_index": page_index,
                    "image_path": f"page_{page_index:03d}.png",
                }
            )


def _make_primary_artifacts(
    omr_dir: Path,
    midi_dir: Path,
    page_indexes: tuple[int, ...],
) -> None:
    for page_index in page_indexes:
        page_dir = omr_dir / "doc-a" / f"page_{page_index:03d}"
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / f"page_{page_index:03d}.mxl").write_bytes(b"mxl")
        midi_path = midi_dir / "doc-a" / f"page_{page_index:03d}.mid"
        midi_path.parent.mkdir(parents=True, exist_ok=True)
        midi_path.write_bytes(b"midi")


class RunOmrEvalPipelineTests(unittest.TestCase):
    def test_pipeline_runs_stages_and_calculates_combined_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sample = root / "sample.csv"
            _write_sample(sample)
            calls = []

            def primary(rows, **kwargs):
                calls.append(("primary", len(rows), kwargs["resume"]))
                _make_primary_artifacts(
                    kwargs["omr_dir"], kwargs["midi_dir"], (1, 2)
                )
                return []

            def fallback(pages, **kwargs):
                calls.append(("fallback", len(pages), kwargs["resume"]))
                mxl = kwargs["out_dir"] / "doc-a/page_003/page_003.mxl"
                midi = kwargs["midi_dir"] / "doc-a/page_003.mid"
                mxl.parent.mkdir(parents=True, exist_ok=True)
                midi.parent.mkdir(parents=True, exist_ok=True)
                mxl.write_bytes(b"mxl")
                midi.write_bytes(b"midi")
                return [
                    {
                        "doc_id": "doc-a",
                        "page_index": 3,
                        "fallback_400_status": "recovered_midi",
                        "fallback_400_mxl_path": str(mxl),
                        "fallback_400_midi_path": str(midi),
                    },
                    {
                        "doc_id": "doc-a",
                        "page_index": 4,
                        "fallback_400_status": "still_failed",
                        "fallback_400_mxl_path": "",
                        "fallback_400_midi_path": "",
                    },
                ]

            def preprocessing(pages, **kwargs):
                calls.append(("preprocessing", len(pages), kwargs["resume"]))
                mxl = kwargs["out_dir"] / "doc-a/page_004/crop/page_004.mxl"
                mxl.parent.mkdir(parents=True, exist_ok=True)
                mxl.write_bytes(b"mxl")
                return [
                    {
                        "doc_id": "doc-a",
                        "page_index": 4,
                        "variant": "crop_page",
                        "preprocessing_fallback_status": "recovered_mxl",
                        "preprocessing_mxl_path": str(mxl),
                        "preprocessing_midi_path": "",
                    }
                ]

            result = run_omr_eval_pipeline(
                sample,
                pages_dir=root / "pages",
                raw_dir=root / "raw",
                out_root=root / "pipeline",
                reports_dir=root / "reports",
                resume=True,
                primary_runner=primary,
                fallback_runner=fallback,
                preprocessing_runner=preprocessing,
            )

            summary = result["summary"]
            self.assertEqual(summary["sampled_pages"], 4)
            self.assertEqual(summary["primary_mxl_pages"], 2)
            self.assertEqual(summary["fallback_400_recovered_mxl"], 1)
            self.assertEqual(summary["preprocessing_recovered_mxl"], 1)
            self.assertEqual(summary["final_combined_mxl_pages"], 4)
            self.assertEqual(summary["final_combined_midi_pages"], 3)
            self.assertEqual(summary["still_failed_pages"], 0)
            self.assertEqual(
                calls,
                [
                    ("primary", 4, True),
                    ("fallback", 2, True),
                    ("preprocessing", 1, True),
                ],
            )
            self.assertTrue(result["paths"]["combined_report"].is_file())
            self.assertTrue(result["paths"]["summary"].is_file())

    def test_resume_is_forwarded_to_all_stage_runners(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sample = root / "sample.csv"
            _write_sample(sample, pages=1)
            resume_values = []

            def primary(rows, **kwargs):
                resume_values.append(kwargs["resume"])
                _make_primary_artifacts(
                    kwargs["omr_dir"], kwargs["midi_dir"], (1,)
                )
                return []

            def empty_stage(pages, **kwargs):
                resume_values.append(kwargs["resume"])
                return []

            run_omr_eval_pipeline(
                sample,
                pages_dir=root / "pages",
                raw_dir=root / "raw",
                out_root=root / "pipeline",
                reports_dir=root / "reports",
                resume=True,
                primary_runner=primary,
                fallback_runner=empty_stage,
                preprocessing_runner=empty_stage,
            )

            self.assertEqual(resume_values, [True, True, True])

    def test_combined_metric_calculation(self) -> None:
        rows = [
            {
                "doc_id": "doc-a",
                "page_index": 1,
                "primary_has_mxl": True,
                "primary_has_midi": True,
                "fallback_400_has_mxl": False,
                "fallback_400_has_midi": False,
                "preprocessing_has_mxl": False,
                "preprocessing_has_midi": False,
                "final_has_mxl": True,
                "final_has_midi": True,
            },
            {
                "doc_id": "doc-a",
                "page_index": 2,
                "primary_has_mxl": False,
                "primary_has_midi": False,
                "fallback_400_has_mxl": True,
                "fallback_400_has_midi": True,
                "preprocessing_has_mxl": False,
                "preprocessing_has_midi": False,
                "final_has_mxl": True,
                "final_has_midi": True,
            },
            {
                "doc_id": "doc-a",
                "page_index": 3,
                "primary_has_mxl": False,
                "primary_has_midi": False,
                "fallback_400_has_mxl": False,
                "fallback_400_has_midi": False,
                "preprocessing_has_mxl": False,
                "preprocessing_has_midi": False,
                "final_has_mxl": False,
                "final_has_midi": False,
            },
        ]
        fallback = [
            {"doc_id": "doc-a", "page_index": 2},
            {"doc_id": "doc-a", "page_index": 3},
        ]

        summary = calculate_combined_summary(rows, fallback, [])

        self.assertEqual(summary["primary_mxl_pages"], 1)
        self.assertEqual(summary["fallback_400_attempted_pages"], 2)
        self.assertEqual(summary["final_combined_mxl_pages"], 2)
        self.assertAlmostEqual(
            summary["final_combined_mxl_success_rate"], 2 / 3
        )
        self.assertEqual(summary["still_failed_pages"], 1)


if __name__ == "__main__":
    unittest.main()
