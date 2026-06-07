"""Tests for MXL to MIDI conversion."""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from convert_mxl_to_midi import (
    build_batch_midi_path,
    convert_mxl_batch,
    convert_mxl_to_midi,
    find_mxl_files,
)


class FakeExpanderException(Exception):
    pass


class FakeFlatStream:
    def __init__(self, output: Path) -> None:
        self.output = output

    def write(self, format_name: str, fp: str) -> None:
        Path(fp).write_bytes(b"midi")


class FakeNotesAndRests:
    def stream(self) -> FakeFlatStream:
        return FakeFlatStream(Path())


class FakeFlattened:
    notesAndRests = FakeNotesAndRests()


class FallbackScore:
    def __init__(self, write_error: Exception | None = None) -> None:
        self.write_error = write_error

    def write(self, format_name: str, fp: str) -> None:
        if self.write_error is not None:
            raise self.write_error
        Path(fp).write_bytes(b"midi")

    def flatten(self) -> FakeFlattened:
        return FakeFlattened()


class MxlToMidiTests(unittest.TestCase):
    def test_builds_batch_output_path(self) -> None:
        input_dir = Path("outputs/omr_300dpi")
        source = (
            input_dir
            / "rsl01001872102"
            / "page_013"
            / "page_013.mxl"
        )

        output = build_batch_midi_path(source, input_dir, Path("outputs/midi"))

        self.assertEqual(
            output,
            Path("outputs/midi/rsl01001872102/page_013.mid"),
        )

    def test_batch_finds_mxl_files_recursively(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            first = root / "doc-a" / "page_001" / "page_001.mxl"
            second = root / "doc-b" / "page_002" / "page_002.mxl"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            first.touch()
            second.touch()

            files = find_mxl_files(root)

            self.assertEqual(files, [first, second])

    def test_flat_fallback_completes_after_repeat_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            source = root / "page.mxl"
            midi = root / "page.mid"
            source.touch()
            parsed_scores = iter(
                [
                    FallbackScore(FakeExpanderException("bad repeat")),
                    FallbackScore(RuntimeError("still bad")),
                    FallbackScore(),
                ]
            )

            result = convert_mxl_to_midi(
                source,
                midi,
                parser=lambda _: next(parsed_scores),
                expander_exception=FakeExpanderException,
                repeat_cleaner=lambda score: None,
            )

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["mode"], "flat_fallback")
            self.assertTrue(midi.is_file())

    def test_batch_report_contains_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            input_dir = root / "omr"
            source = input_dir / "doc" / "page_001" / "page_001.mxl"
            source.parent.mkdir(parents=True)
            source.touch()

            def fake_converter(source_mxl: Path, midi_path: Path) -> dict[str, str]:
                return {
                    "source_mxl": str(source_mxl),
                    "midi_path": str(midi_path),
                    "status": "success",
                    "message": "",
                    "mode": "normal",
                }

            report = convert_mxl_batch(
                input_dir,
                root / "midi",
                converter_func=fake_converter,
            )

            self.assertIn("status", report.columns)
            self.assertEqual(report.iloc[0]["status"], "success")


if __name__ == "__main__":
    unittest.main()
