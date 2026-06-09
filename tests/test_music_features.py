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
            self.assertEqual(row["time_signatures"], "4/4")
            self.assertEqual(row["measures_count"], 1)
            self.assertEqual(row["source"], "musicxml")
            self.assertEqual(row["confidence"], 1.0)

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

    def test_invalid_musicxml_returns_parse_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rsl01000000001" / "page_004.musicxml"
            path.parent.mkdir()
            path.write_text("<broken>", encoding="utf-8")

            row = extract_music_features(path)

            self.assertEqual(row["extraction_status"], "parse_error")
            self.assertEqual(row["confidence"], 0.0)
            self.assertTrue(row["error"])

    def test_missing_file_returns_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rsl01000000001" / "page_099.mxl"

            row = extract_music_features(path)

            self.assertEqual(row["extraction_status"], "missing_file")
            self.assertEqual(row["confidence"], 0.0)
            self.assertIn("File not found", row["error"])

    def test_missing_key_is_unknown_without_crash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rsl01000000001" / "page_005.musicxml"
            write_musicxml(path, fifths=None)

            row = extract_music_features(path)

            self.assertEqual(row["extraction_status"], "no_key")
            self.assertEqual(row["key_name_latin"], "unknown")
            self.assertEqual(row["key_name_ru"], "unknown")
            self.assertEqual(row["source"], "not_found")
            self.assertEqual(row["confidence"], 0.6)

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
            self.assertEqual(row["confidence"], 1.0)

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
            broken = (
                input_dir
                / "rsl01000000001"
                / "page_007"
                / "page_007.musicxml"
            )
            broken.parent.mkdir(parents=True)
            broken.write_text("<broken>", encoding="utf-8")
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
            self.assertEqual(len(rows), 2)
            self.assertEqual(
                {row["extraction_status"] for row in rows},
                {"success", "parse_error"},
            )
            self.assertIn("Files processed: 2", summary_text)
            self.assertIn("без mode", summary_text)

    def test_cli_reads_omr_report_and_preserves_midi_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = (
                root
                / "omr"
                / "rsl01000000001"
                / "page_008"
                / "page_008.musicxml"
            )
            write_musicxml(source)
            midi = root / "midi" / "rsl01000000001" / "page_008.mid"
            midi.parent.mkdir(parents=True)
            midi.write_bytes(b"MThd")
            report = root / "omr_report.csv"
            with report.open("w", encoding="utf-8", newline="") as csv_file:
                writer = csv.DictWriter(
                    csv_file,
                    fieldnames=[
                        "doc_id",
                        "page_index",
                        "mxl_path",
                        "midi_path",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "doc_id": "rsl01000000001",
                        "page_index": 8,
                        "mxl_path": source,
                        "midi_path": midi,
                    }
                )
                writer.writerow(
                    {
                        "doc_id": "rsl01000000002",
                        "page_index": 9,
                        "mxl_path": root / "missing" / "page_009.mxl",
                        "midi_path": "",
                    }
                )
            output = root / "reports" / "music_features.csv"

            result = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "scripts" / "extract_music_features.py"),
                    "--omr-report",
                    str(report),
                    "--out",
                    str(output),
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            with output.open(encoding="utf-8", newline="") as csv_file:
                rows = list(csv.DictReader(csv_file))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["midi_path"], str(midi))
            self.assertEqual(rows[0]["extraction_status"], "success")
            self.assertEqual(rows[1]["extraction_status"], "missing_file")
            self.assertTrue(
                output.with_name("music_features_summary.md").is_file()
            )


if __name__ == "__main__":
    unittest.main()
