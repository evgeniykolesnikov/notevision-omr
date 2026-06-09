"""Tests for the corpus-analysis orchestrator."""

import argparse
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from scripts.run_corpus_analysis import (
    CommandResult,
    build_document_commands,
    build_static_commands,
    run_corpus_analysis,
    write_run_reports,
)


def make_args(root: Path, **updates: object) -> argparse.Namespace:
    values = {
        "inbox": root / "data" / "inbox",
        "raw_dir": root / "data" / "raw",
        "pages_dir": root / "outputs" / "pages",
        "labels_dir": root / "data" / "labels",
        "reports_dir": root / "outputs" / "reports",
        "docs_dir": root / "docs" / "thesis",
        "dpi": 200,
        "resume": False,
        "skip_existing": False,
        "limit_docs": None,
        "doc_id": None,
        "dry_run": False,
        "fail_fast": False,
        "continue_on_error": True,
        "prepare_omr_sample": False,
        "run_omr": False,
        "omr_sample_limit": 150,
        "random_seed": 42,
        "audiveris_bin": "audiveris",
    }
    values.update(updates)
    return argparse.Namespace(**values)


class CorpusAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_dir.name)
        (self.root / "data" / "inbox").mkdir(parents=True)
        document = self.root / "data" / "raw" / "rsl001"
        document.mkdir(parents=True)
        (document / "source.pdf").write_bytes(b"pdf")

    def tearDown(self) -> None:
        self.temporary_dir.cleanup()

    def test_dry_run_creates_no_files_and_prints_plan(self) -> None:
        args = make_args(self.root, dry_run=True)
        output = io.StringIO()

        with redirect_stdout(output):
            logs, _ = run_corpus_analysis(args)

        self.assertIn("[1/7] Organizing inbox", output.getvalue())
        self.assertIn("DRY-RUN", output.getvalue())
        self.assertTrue(logs)
        self.assertTrue(all(row["status"] == "planned" for row in logs))
        self.assertFalse(args.reports_dir.exists())
        self.assertFalse(args.labels_dir.exists())

    def test_subprocess_commands_are_built_with_expected_contracts(self) -> None:
        args = make_args(self.root)
        static = build_static_commands(args)
        extraction, detection = build_document_commands(
            [args.raw_dir / "rsl001"],
            args,
        )

        self.assertIn("organize_raw_files.py", static["organize"][0][1])
        self.assertIn("--raw-dir", static["inventory"][0])
        self.assertIn("build_labels_template.py", static["labels"][0][1])
        self.assertIn("--document-dir", extraction[0])
        self.assertIn("--dpi", extraction[0])
        self.assertIn("run_pipeline.py", detection[0][1])
        self.assertIn("--manifest", detection[0])

    def test_summary_files_are_created(self) -> None:
        args = make_args(self.root)
        args.labels_dir.mkdir(parents=True)
        args.reports_dir.mkdir(parents=True)
        (args.labels_dir / "document_inventory.csv").write_text(
            "doc_id,pdf_status,mrc_status\nrsl001,exists,parsed\n",
            encoding="utf-8",
        )
        (args.reports_dir / "dataset_statistics.csv").write_text(
            "total_pages,music,mixed,title,text,blank,bad_scan,unknown\n"
            "10,4,1,1,2,1,0,1\n",
            encoding="utf-8",
        )
        summary = {
            "documents": 1,
            "pdf_exists": 1,
            "mrc_parsed": 1,
            "total_pages": 10,
            "page_types": {
                "music": 4,
                "mixed": 1,
                "title": 1,
                "text": 2,
                "blank": 1,
                "bad_scan": 0,
                "unknown": 1,
            },
            "skipped_missing_pdf": 0,
            "skipped_missing_mrc": 0,
            "incomplete_documents": 0,
            "errors": 0,
        }

        log_path, summary_path = write_run_reports(args, [], summary)

        self.assertTrue(log_path.is_file())
        self.assertTrue(summary_path.is_file())
        self.assertIn("Страниц всего | 10", summary_path.read_text(encoding="utf-8"))

    def test_fail_fast_stops_after_first_failed_stage(self) -> None:
        args = make_args(self.root, fail_fast=True, continue_on_error=False)
        calls = []

        def runner(command):
            calls.append(list(command))
            return CommandResult(list(command), 1, stderr="import failed")

        logs, summary = run_corpus_analysis(args, runner=runner)

        self.assertEqual(len(calls), 1)
        self.assertEqual(logs[0]["stage"], "organize")
        self.assertEqual(summary["errors"], 1)

    def test_continue_on_error_runs_later_stages(self) -> None:
        args = make_args(self.root, continue_on_error=True)
        calls = []

        def runner(command):
            calls.append(list(command))
            if "organize_raw_files.py" in command[1]:
                return CommandResult(list(command), 1, stderr="import failed")
            if "build_document_inventory.py" in command[1]:
                args.labels_dir.mkdir(parents=True, exist_ok=True)
                (args.labels_dir / "document_inventory.csv").write_text(
                    "doc_id,pdf_status,mrc_status\nrsl001,exists,parsed\n",
                    encoding="utf-8",
                )
            if "extract_pages.py" in command[1]:
                output_dir = Path(command[command.index("--out") + 1])
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / "manifest.csv").write_text(
                    "doc_id,page_index,image_path\nrsl001,1,page.png\n",
                    encoding="utf-8",
                )
            return CommandResult(list(command), 0, stdout="ok")

        logs, summary = run_corpus_analysis(args, runner=runner)

        called_scripts = {Path(command[1]).name for command in calls}
        self.assertIn("organize_raw_files.py", called_scripts)
        self.assertIn("build_document_inventory.py", called_scripts)
        self.assertIn("extract_pages.py", called_scripts)
        self.assertIn("run_pipeline.py", called_scripts)
        self.assertEqual(summary["errors"], 1)
        self.assertTrue(
            (args.reports_dir / "corpus_analysis_run_log.csv").is_file()
        )

    def test_missing_pdf_is_skipped_without_pipeline_error(self) -> None:
        args = make_args(self.root, continue_on_error=True)
        mrc_only = args.raw_dir / "rsl002"
        mrc_only.mkdir(parents=True)
        (mrc_only / "record.mrc").write_bytes(b"mrc")
        calls = []

        def runner(command):
            calls.append(list(command))
            if "build_document_inventory.py" in command[1]:
                args.labels_dir.mkdir(parents=True, exist_ok=True)
                (args.labels_dir / "document_inventory.csv").write_text(
                    "doc_id,pdf_status,mrc_status\n"
                    "rsl001,exists,parsed\n"
                    "rsl002,missing,parsed\n",
                    encoding="utf-8",
                )
            if "extract_pages.py" in command[1]:
                output_dir = Path(command[command.index("--out") + 1])
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / "manifest.csv").write_text(
                    "doc_id,page_index,image_path\nrsl001,1,page.png\n",
                    encoding="utf-8",
                )
            return CommandResult(list(command), 0, stdout="ok")

        logs, summary = run_corpus_analysis(args, runner=runner)

        extraction_commands = [
            command for command in calls if "extract_pages.py" in command[1]
        ]
        detector_commands = [
            command for command in calls if "run_pipeline.py" in command[1]
        ]
        self.assertEqual(len(extraction_commands), 1)
        self.assertNotIn("rsl002", " ".join(extraction_commands[0]))
        self.assertEqual(len(detector_commands), 1)
        self.assertNotIn("rsl002", " ".join(detector_commands[0]))
        skipped = [
            row
            for row in logs
            if row["status"] == "skipped_incomplete"
            and "rsl002" in str(row["message"])
        ]
        self.assertEqual(len(skipped), 2)
        self.assertEqual(summary["skipped_missing_pdf"], 1)
        self.assertEqual(summary["incomplete_documents"], 1)
        self.assertEqual(summary["errors"], 0)

    def test_missing_manifest_skips_detector(self) -> None:
        args = make_args(self.root, continue_on_error=True)
        calls = []

        def runner(command):
            calls.append(list(command))
            if "build_document_inventory.py" in command[1]:
                args.labels_dir.mkdir(parents=True, exist_ok=True)
                (args.labels_dir / "document_inventory.csv").write_text(
                    "doc_id,pdf_status,mrc_status\nrsl001,exists,parsed\n",
                    encoding="utf-8",
                )
            return CommandResult(list(command), 0, stdout="ok")

        logs, summary = run_corpus_analysis(args, runner=runner)

        self.assertFalse(
            any("run_pipeline.py" in command[1] for command in calls)
        )
        self.assertTrue(
            any(
                row["stage"] == "detector"
                and row["status"] == "skipped_incomplete"
                and "manifest.csv is missing" in str(row["message"])
                for row in logs
            )
        )
        self.assertEqual(summary["errors"], 0)


if __name__ == "__main__":
    unittest.main()
