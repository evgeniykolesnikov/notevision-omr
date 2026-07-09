"""Smoke tests for safe parallel OMR batch runner."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_omr_batch_parallel.py"


def load_script():
    spec = importlib.util.spec_from_file_location("run_omr_batch_parallel", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load run_omr_batch_parallel.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RunOmrBatchParallelTests(unittest.TestCase):
    def test_script_imports(self) -> None:
        module = load_script()
        self.assertTrue(hasattr(module, "select_pages"))

    def test_stats_empty(self) -> None:
        module = load_script()
        self.assertEqual(
            module.stats([]),
            {"mean": 0.0, "median": 0.0, "min": 0.0, "max": 0.0},
        )


if __name__ == "__main__":
    unittest.main()
