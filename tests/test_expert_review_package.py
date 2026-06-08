"""Tests for the external expert review package builder."""

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "build_expert_review_package.py"
SPEC = importlib.util.spec_from_file_location(
    "build_expert_review_package",
    SCRIPT_PATH,
)
assert SPEC is not None and SPEC.loader is not None
package = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package)


def write_sample(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(
            destination,
            fieldnames=["doc_id", "page_index", "image_path"],
        )
        writer.writeheader()
        writer.writerows(rows)


class ExpertReviewPackageTests(unittest.TestCase):
    def test_builds_page_files_review_csv_and_readme(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            sample_path = root / "sample.csv"
            scan = root / "outputs" / "pages" / "doc-a" / "page_002.png"
            midi = root / "outputs" / "midi" / "doc-a" / "page_002.mid"
            scan.parent.mkdir(parents=True)
            midi.parent.mkdir(parents=True)
            scan.write_bytes(b"scan")
            midi.write_bytes(b"midi")
            write_sample(
                sample_path,
                [
                    {
                        "doc_id": "doc-a",
                        "page_index": 2,
                        "image_path": "outputs/pages/doc-a/page_002.png",
                    }
                ],
            )

            output_dir = root / "package"
            summary = package.build_expert_review_package(
                sample_path,
                output_dir,
                midi_dir=root / "outputs" / "midi",
                project_root=root,
            )

            page_dir = output_dir / "doc-a" / "page_002"
            self.assertEqual((page_dir / "scan.png").read_bytes(), b"scan")
            self.assertEqual((page_dir / "midi.mid").read_bytes(), b"midi")
            self.assertTrue((output_dir / "README.md").is_file())
            self.assertEqual(summary["pages"], 1)

            with (output_dir / "expert_review.csv").open(
                encoding="utf-8-sig",
                newline="",
            ) as source:
                reader = csv.DictReader(source)
                rows = list(reader)
            self.assertEqual(reader.fieldnames, package.REVIEW_COLUMNS)
            self.assertEqual(rows[0]["doc_id"], "doc-a")
            self.assertEqual(rows[0]["page_index"], "2")
            self.assertEqual(rows[0]["usable"], "")

    def test_missing_midi_rejects_package_before_output_is_created(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            sample_path = root / "sample.csv"
            scan = root / "scan.png"
            scan.write_bytes(b"scan")
            write_sample(
                sample_path,
                [
                    {
                        "doc_id": "doc-a",
                        "page_index": 1,
                        "image_path": str(scan),
                    }
                ],
            )
            output_dir = root / "package"

            with self.assertRaisesRegex(FileNotFoundError, "MIDI"):
                package.build_expert_review_package(
                    sample_path,
                    output_dir,
                    midi_dir=root / "midi",
                    project_root=root,
                )

            self.assertFalse(output_dir.exists())

    def test_non_empty_output_requires_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            sample_path = root / "sample.csv"
            scan = root / "scan.png"
            midi = root / "midi" / "doc-a" / "page_001.mid"
            scan.write_bytes(b"scan")
            midi.parent.mkdir(parents=True)
            midi.write_bytes(b"midi")
            write_sample(
                sample_path,
                [
                    {
                        "doc_id": "doc-a",
                        "page_index": 1,
                        "image_path": str(scan),
                    }
                ],
            )
            output_dir = root / "package"
            output_dir.mkdir()
            (output_dir / "existing.txt").write_text("keep", encoding="utf-8")

            with self.assertRaisesRegex(FileExistsError, "--overwrite"):
                package.build_expert_review_package(
                    sample_path,
                    output_dir,
                    midi_dir=root / "midi",
                    project_root=root,
                )

    def test_readme_contains_rating_instructions(self) -> None:
        readme = package.build_readme(30)
        self.assertIn("30 страниц", readme)
        self.assertIn("pitch_quality", readme)
        self.assertIn("duration_quality", readme)
        self.assertIn("usable=no", readme)


if __name__ == "__main__":
    unittest.main()
