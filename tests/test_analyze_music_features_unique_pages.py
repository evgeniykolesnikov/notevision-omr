"""Tests for unique-page music feature analysis."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "analyze_music_features_unique_pages.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "analyze_music_features_unique_pages",
        SCRIPT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load analyze_music_features_unique_pages.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class UniquePageMusicFeatureTests(unittest.TestCase):
    def test_key_candidates_for_zero_accidentals(self) -> None:
        module = load_module()

        self.assertEqual(module.key_candidates(0), "C major / A minor")

    def test_variant_priority_prefers_fallback_over_primary(self) -> None:
        module = load_module()

        primary_variant, primary_priority = module.classify_variant(
            Path("outputs/omr_eval_300/rsl01000000001/page_001/page_001.mxl")
        )
        fallback_variant, fallback_priority = module.classify_variant(
            Path("outputs/omr_eval_300_400dpi_fallback/rsl01000000001/page_001/page_001_400dpi.mxl")
        )

        self.assertEqual(primary_variant, "primary")
        self.assertEqual(fallback_variant, "400dpi_fallback")
        self.assertLess(fallback_priority, primary_priority)

    def test_omr_300dpi_is_primary_variant(self) -> None:
        module = load_module()

        variant, _ = module.classify_variant(
            Path("outputs/omr_300dpi/rsl01000000001/page_001/page_001.mxl")
        )

        self.assertEqual(variant, "primary")

    def test_summary_counts_unique_pages(self) -> None:
        module = load_module()
        rows = [
            {
                "mxl_exists": 1,
                "midi_exists": 1,
                "extraction_status": "success",
                "explicit_key_signature_found": 1,
                "zero_key_signature": 1,
                "key_candidates": "C major / A minor",
                "key_name_inferred": "",
                "time_signature_found": 1,
                "clefs_found": 1,
                "parts_found": 1,
                "instruments_found": 1,
                "measures_count_found": 1,
                "page_type": "music",
                "parse_extract_duration_ms": 10,
            },
            {
                "mxl_exists": 0,
                "midi_exists": 0,
                "extraction_status": "no_mxl",
                "explicit_key_signature_found": 0,
                "zero_key_signature": 0,
                "key_candidates": "",
                "key_name_inferred": "",
                "time_signature_found": 0,
                "clefs_found": 0,
                "parts_found": 0,
                "instruments_found": 0,
                "measures_count_found": 0,
                "page_type": "text",
                "parse_extract_duration_ms": 0,
            },
        ]

        summary = module.summarize(rows, [])

        self.assertEqual(summary["total_validated_pages"], 2)
        self.assertEqual(summary["pages_with_mxl"], 1)
        self.assertEqual(summary["explicit_key"], 1)
        self.assertEqual(summary["zero_key"], 1)
        self.assertEqual(summary["total_music_mixed_pages"], 1)
        self.assertEqual(summary["music_mixed_with_features"], 1)

    def test_script_imports(self) -> None:
        module = load_module()

        self.assertTrue(hasattr(module, "find_artifacts"))


if __name__ == "__main__":
    unittest.main()
