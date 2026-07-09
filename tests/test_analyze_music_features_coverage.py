"""Tests for music feature coverage analysis."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "analyze_music_features_coverage.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "analyze_music_features_coverage",
        SCRIPT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load analyze_music_features_coverage.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_musicxml(path: Path, *, include_key: bool = True) -> None:
    key_xml = "<key><fifths>0</fifths><mode>major</mode></key>" if include_key else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list>
    <score-part id="P1">
      <part-name>Piano</part-name>
      <score-instrument id="P1-I1"><instrument-name>Piano</instrument-name></score-instrument>
    </score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        {key_xml}
        <time><beats>4</beats><beat-type>4</beat-type></time>
        <clef><sign>G</sign><line>2</line></clef>
      </attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration><type>quarter</type></note>
    </measure>
  </part>
</score-partwise>
""",
        encoding="utf-8",
    )


class MusicFeatureCoverageTests(unittest.TestCase):
    def test_script_imports(self) -> None:
        module = load_module()

        self.assertTrue(hasattr(module, "find_existing_musicxml_files"))

    def test_small_musicxml_sample_is_processed(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "outputs" / "omr" / "rsl01000000001" / "page_001" / "page_001.musicxml"
            write_musicxml(path)

            row = module.analyze_one(path)

            self.assertEqual(row["doc_id"], "rsl01000000001")
            self.assertEqual(row["page_index"], "1")
            self.assertEqual(row["has_key_signature"], 1)
            self.assertEqual(row["has_time_signature"], 1)
            self.assertEqual(row["has_clefs"], 1)
            self.assertEqual(row["has_parts"], 1)

    def test_missing_file_does_not_break_summary(self) -> None:
        module = load_module()
        row = module.analyze_one(Path("missing") / "rsl01000000001" / "page_099.mxl")
        summary = module.summarize([row])

        self.assertEqual(row["extraction_status"], "failed")
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["parsed_success"], 0)
        self.assertEqual(summary["parsed_failed"], 1)

    def test_coverage_counters(self) -> None:
        module = load_module()
        rows = [
            {
                "extraction_status": "success",
                "has_key_signature": 1,
                "has_time_signature": 1,
                "has_clefs": 1,
                "has_parts": 1,
                "has_instruments": 0,
                "measures_count": 1,
                "midi_exists": 1,
                "duration_ms": 10,
            },
            {
                "extraction_status": "no_key",
                "has_key_signature": 0,
                "has_time_signature": 1,
                "has_clefs": 0,
                "has_parts": 1,
                "has_instruments": 1,
                "measures_count": 0,
                "midi_exists": 0,
                "duration_ms": 20,
            },
        ]

        summary = module.summarize(rows)

        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["parsed_success"], 2)
        self.assertEqual(summary["key_count"], 1)
        self.assertEqual(summary["time_count"], 2)
        self.assertEqual(summary["midi_count"], 1)
        self.assertEqual(summary["mean_ms"], 15.0)


if __name__ == "__main__":
    unittest.main()
