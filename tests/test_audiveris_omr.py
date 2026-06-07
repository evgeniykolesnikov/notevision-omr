"""Tests for the experimental Audiveris integration."""

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from notevision.omr.audiveris import (
    build_audiveris_command,
    run_audiveris,
    run_audiveris_batch,
    run_audiveris_candidates,
)


class AudiverisOmrTests(unittest.TestCase):
    def test_build_audiveris_command(self) -> None:
        command = build_audiveris_command(
            "page.png",
            "outputs/omr/doc",
            audiveris_bin="audiveris-cli",
        )

        self.assertEqual(command[0], "audiveris-cli")
        self.assertIn("-batch", command)
        self.assertIn("-transcribe", command)
        self.assertIn("-export", command)
        self.assertEqual(command[-2:], ["--", "page.png"])

    def test_missing_audiveris_binary_returns_failed_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            input_path = root / "page.png"
            input_path.write_bytes(b"image")

            result = run_audiveris(
                input_path,
                root / "omr",
                audiveris_bin="definitely-missing-audiveris-command",
            )

            self.assertEqual(result["status"], "failed")
            self.assertIn("was not found", result["message"])
            self.assertTrue(Path(result["log_path"]).is_file())

    def test_batch_limit_restricts_number_of_pages(self) -> None:
        labels = pd.DataFrame(
            {
                "doc_id": ["doc-a", "doc-a", "doc-b", "doc-b"],
                "page_index": [1, 2, 1, 2],
                "has_music": [1, 0, 1, 1],
            }
        )
        calls: list[Path] = []

        def fake_runner(
            input_path: Path,
            out_dir: Path,
            audiveris_bin: str = "audiveris",
        ) -> dict[str, object]:
            calls.append(Path(input_path))
            return {"status": "success", "message": ""}

        report = run_audiveris_batch(
            labels,
            "preprocessed",
            "omr",
            limit=2,
            runner=fake_runner,
        )

        self.assertEqual(len(report), 2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(
            [path.as_posix() for path in calls],
            [
                "preprocessed/doc-a/page_001_binary.png",
                "preprocessed/doc-b/page_001_binary.png",
            ],
        )

    def test_candidates_batch_uses_paths_skips_missing_and_applies_limit(
        self,
    ) -> None:
        candidates = pd.DataFrame(
            {
                "doc_id": ["doc-a", "doc-a", "doc-b", "doc-c"],
                "page_index": [2, 3, 7, 1],
                "preprocessed_path": [
                    "prepared/custom-a.png",
                    "prepared/skip.png",
                    "prepared/custom-b.png",
                    "prepared/limited.png",
                ],
                "exists": [True, False, "True", True],
            }
        )
        calls: list[tuple[Path, Path]] = []

        def fake_runner(
            input_path: Path,
            out_dir: Path,
            audiveris_bin: str = "audiveris",
        ) -> dict[str, object]:
            calls.append((Path(input_path), Path(out_dir)))
            return {"status": "success", "message": ""}

        report = run_audiveris_candidates(
            candidates,
            "outputs/omr",
            limit=2,
            runner=fake_runner,
        )

        self.assertEqual(len(report), 2)
        self.assertEqual(
            [input_path.as_posix() for input_path, _ in calls],
            ["prepared/custom-a.png", "prepared/custom-b.png"],
        )
        self.assertEqual(
            [output_dir.as_posix() for _, output_dir in calls],
            [
                "outputs/omr/doc-a/page_002",
                "outputs/omr/doc-b/page_007",
            ],
        )
        self.assertNotIn("prepared/skip.png", report["input_path"].tolist())


if __name__ == "__main__":
    unittest.main()
