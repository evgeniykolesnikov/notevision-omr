"""Tests for MusicXML music-theoretical feature extraction."""

from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from notevision.music_features import (
    FEATURE_COLUMNS,
    extract_music_features,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def write_musicxml(
    path: Path,
    *,
    fifths: int | None = 0,
    mode: str | None = "major",
    time_signature: str = "4/4",
    clefs: tuple[tuple[str, int], ...] = (("G", 2),),
    part_name: str = "Piano",
) -> None:
    beats, beat_type = time_signature.split("/")
    key_xml = ""
    if fifths is not None:
        mode_xml = f"<mode>{mode}</mode>" if mode else ""
        key_xml = f"<key><fifths>{fifths}</fifths>{mode_xml}</key>"
    clef_xml = "".join(
        f"<clef number=\"{index}\"><sign>{sign}</sign><line>{line}</line></clef>"
        for index, (sign, line) in enumerate(clefs, start=1)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN"
  "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="3.1">
  <part-list>
    <score-part id="P1">
      <part-name>{part_name}</part-name>
      <score-instrument id="P1-I1"><instrument-name>{part_name}</instrument-name></score-instrument>
    </score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        {key_xml}
        <time><beats>{beats}</beats><beat-type>{beat_type}</beat-type></time>
        <staves>{len(clefs)}</staves>
        {clef_xml}
      </attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration><type>quarter</type></note>
    </measure>
  </part>
</score-partwise>
""",
        encoding="utf-8",
    )


class MusicFeaturesTests(unittest.TestCase):
    def test_c_major_and_time_signature_are_extracted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = (
                Path(temp_dir)
                / "rsl01000000001"
                / "page_001"
                / "page_001.musicxml"
            )
            write_musicxml(path)

            row = extract_music_features(path)

            self.assertEqual(row["extraction_status"], "success")
            self.assertEqual(row["key_name_latin"], "C-dur")
            self.assertEqual(row["key_name_ru"], "до мажор")
            self.assertEqual(row["detected_tonality_latin"], "C-dur")
            self.assertEqual(row["detected_tonality_ru"], "до мажор")
            self.assertEqual(row["mode_status"], "detected")
            self.assertEqual(row["time_signature"], "4/4")
            self.assertEqual(row["source"], "musicxml")
            self.assertEqual(row["confidence"], "high")

    def test_a_minor_is_extracted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rsl01000000001" / "page_002.musicxml"
            write_musicxml(path, fifths=0, mode="minor")

            row = extract_music_features(path)

            self.assertEqual(row["key_name_latin"], "a-moll")
            self.assertEqual(row["key_name_ru"], "ля минор")
            self.assertEqual(row["detected_tonality_latin"], "a-moll")
            self.assertEqual(row["detected_tonality_ru"], "ля минор")
            self.assertEqual(row["mode_status"], "detected")

    def test_treble_and_bass_clefs_are_translated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rsl01000000001" / "page_003.xml"
            write_musicxml(path, clefs=(("G", 2), ("F", 4)))

            row = extract_music_features(path)

            self.assertEqual(row["clefs"], "скрипичный;басовый")
            self.assertEqual(row["parts_count"], 1)
            self.assertIn("Piano", row["instruments"])

    def test_invalid_musicxml_returns_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rsl01000000001" / "page_004.musicxml"
            path.parent.mkdir()
            path.write_text("<broken>", encoding="utf-8")

            row = extract_music_features(path)

            self.assertEqual(row["extraction_status"], "failed")
            self.assertTrue(row["error"])

    def test_missing_key_is_unknown_without_crash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rsl01000000001" / "page_005.musicxml"
            write_musicxml(path, fifths=None)

            row = extract_music_features(path)

            self.assertEqual(row["extraction_status"], "partial")
            self.assertEqual(row["key_name_latin"], "unknown")
            self.assertEqual(row["key_name_ru"], "unknown")
            self.assertEqual(row["source"], "not_found")
            self.assertEqual(row["confidence"], "low")

    def test_key_signature_without_mode_lists_both_valid_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rsl01000000001" / "page_007.musicxml"
            write_musicxml(path, fifths=2, mode=None)

            row = extract_music_features(path)

            self.assertEqual(row["mode"], "unknown")
            self.assertEqual(row["key_name_latin"], "D-dur / b-moll")
            self.assertEqual(row["key_name_ru"], "ре мажор / си минор")
            self.assertEqual(
                row["key_signature_name_latin"], "D-dur / b-moll"
            )
            self.assertEqual(
                row["key_signature_name_ru"], "ре мажор / си минор"
            )
            self.assertEqual(row["detected_tonality_latin"], "unknown")
            self.assertEqual(row["detected_tonality_ru"], "unknown")
            self.assertEqual(row["mode_status"], "unknown")
            self.assertEqual(row["source"], "musicxml")
            self.assertEqual(row["confidence"], "high")

    def test_cli_creates_csv_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / "omr"
            write_musicxml(
                input_dir
                / "rsl01000000001"
                / "page_006"
                / "page_006.musicxml"
            )
            output = root / "reports" / "music_features.csv"
            summary = root / "reports" / "music_features_summary.md"

            result = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "scripts" / "extract_music_features.py"),
                    "--mxl-dir",
                    str(input_dir),
                    "--out",
                    str(output),
                    "--summary",
                    str(summary),
                    "--recursive",
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.is_file())
            self.assertTrue(summary.is_file())
            with output.open(encoding="utf-8", newline="") as csv_file:
                rows = list(csv.DictReader(csv_file))
            self.assertEqual(list(rows[0]), FEATURE_COLUMNS)
            self.assertEqual(rows[0]["doc_id"], "rsl01000000001")
            self.assertEqual(rows[0]["page_index"], "6")
            summary_text = summary.read_text(encoding="utf-8")
            self.assertIn("Files processed: 1", summary_text)
            self.assertIn("без mode", summary_text)


if __name__ == "__main__":
    unittest.main()
