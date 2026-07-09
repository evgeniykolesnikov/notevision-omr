"""Smoke tests for the tiny OMR timing benchmark script."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "benchmark_omr_timing_sample.py"


def load_script():
    spec = importlib.util.spec_from_file_location("benchmark_omr_timing_sample", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load benchmark_omr_timing_sample.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OmrTimingSampleScriptTests(unittest.TestCase):
    def test_script_imports(self) -> None:
        module = load_script()
        self.assertTrue(hasattr(module, "select_sample"))

    def test_stats_empty(self) -> None:
        module = load_script()
        self.assertEqual(
            module.stats([]),
            {"mean": 0.0, "median": 0.0, "min": 0.0, "max": 0.0},
        )


if __name__ == "__main__":
    unittest.main()
