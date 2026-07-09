"""Tests for safe pipeline stage benchmark helpers."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "benchmark_pipeline_stages.py"


def load_benchmark_module():
    spec = importlib.util.spec_from_file_location(
        "benchmark_pipeline_stages",
        SCRIPT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load benchmark_pipeline_stages.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class BenchmarkPipelineStagesTests(unittest.TestCase):
    def test_script_imports(self) -> None:
        module = load_benchmark_module()

        self.assertTrue(hasattr(module, "parse_args"))

    def test_timed_call_returns_duration(self) -> None:
        module = load_benchmark_module()

        result, duration_ms, error = module.timed_call(lambda: "ok")

        self.assertEqual(result, "ok")
        self.assertGreaterEqual(duration_ms, 0.0)
        self.assertEqual(error, "")

    def test_binarization_does_not_overwrite_input(self) -> None:
        module = load_benchmark_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "page.png"
            image = np.full((80, 120), 255, dtype=np.uint8)
            image[30, 10:111] = 0
            Image.fromarray(image).save(image_path)
            before = image_path.read_bytes()

            gray = module.load_grayscale_resized(image_path)
            binary = module.otsu_binary(gray)

            self.assertEqual(image_path.read_bytes(), before)
            self.assertEqual(binary.shape, gray.shape)

    def test_missing_musicxml_is_reported_without_crash(self) -> None:
        module = load_benchmark_module()
        missing = Path("missing") / "page_999.mxl"

        row = module.run_music_feature_timing(
            [
                module.MxlSample(
                    doc_id="rsl00000000000",
                    page_index="999",
                    source_path=missing,
                )
            ]
        )[0]

        self.assertEqual(row["stage"], "music_features_extraction")
        self.assertEqual(row["success"], 0)
        self.assertIn("File not found", row["error"])


if __name__ == "__main__":
    unittest.main()
