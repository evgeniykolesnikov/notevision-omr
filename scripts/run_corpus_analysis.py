"""Run the reproducible NoteVision corpus-analysis workflow."""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = PROJECT_ROOT / "scripts"
PAGE_TYPES = ("music", "mixed", "title", "text", "blank", "bad_scan", "unknown")
LOG_COLUMNS = (
    "stage",
    "command",
    "status",
    "returncode",
    "runtime_seconds",
    "message",
)


@dataclass
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""


def _script_command(name: str, *arguments: object) -> list[str]:
    return [sys.executable, str(SCRIPT_DIR / name), *(str(value) for value in arguments)]


def build_static_commands(args: argparse.Namespace) -> dict[str, list[list[str]]]:
    """Build commands that do not depend on the discovered document list."""
    inventory_path = args.labels_dir / "document_inventory.csv"
    all_predictions = args.reports_dir / "all_page_predictions.csv"
    template_path = args.labels_dir / "pages_template_thesis.csv"
    validated_path = args.labels_dir / "pages_validated_thesis.csv"
    statistics_path = args.reports_dir / "dataset_statistics.csv"
    commands: dict[str, list[list[str]]] = {
        "organize": [
            _script_command(
                "organize_raw_files.py",
                "--inbox",
                args.inbox,
                "--raw-dir",
                args.raw_dir,
            )
        ],
        "inventory": [
            _script_command(
                "build_document_inventory.py",
                "--raw-dir",
                args.raw_dir,
                "--out",
                inventory_path,
            )
        ],
        "labels": [
            _script_command(
                "build_labels_template.py",
                "--predictions",
                all_predictions,
                "--out",
                template_path,
                "--overwrite",
            )
        ],
        "statistics": [],
        "reports": [],
        "prepare_omr": [],
        "run_omr": [],
    }
    labels_for_reports = validated_path if validated_path.is_file() else template_path
    commands["statistics"].append(
        _script_command(
            "build_dataset_statistics.py",
            "--labels",
            labels_for_reports,
            "--out",
            statistics_path,
            "--markdown-out",
            args.docs_dir / "dataset_statistics.md",
        )
    )
    if validated_path.is_file():
        commands["labels"].append(
            _script_command(
                "merge_validated_labels.py",
                "--template",
                template_path,
                "--validated",
                validated_path,
                "--out",
                validated_path,
            )
        )
        commands["reports"].extend(
            [
                _script_command(
                    "evaluate_music_detector.py",
                    "--labels",
                    validated_path,
                    "--out",
                    args.reports_dir / "music_detector_metrics.csv",
                ),
                _script_command(
                    "build_detector_error_report.py",
                    "--labels",
                    validated_path,
                    "--out",
                    args.reports_dir / "detector_error_report.csv",
                ),
                _script_command(
                    "build_error_analysis.py",
                    "--labels",
                    validated_path,
                    "--out",
                    args.reports_dir / "error_analysis.csv",
                    "--gallery-out",
                    args.reports_dir / "error_gallery.html",
                ),
            ]
        )
    if args.prepare_omr_sample or args.run_omr:
        sample_path = args.labels_dir / "omr_eval_sample_thesis.csv"
        if (SCRIPT_DIR / "build_omr_eval_sample.py").is_file():
            commands["prepare_omr"].append(
                _script_command(
                    "build_omr_eval_sample.py",
                    "--labels",
                    labels_for_reports,
                    "--out",
                    sample_path,
                    "--limit",
                    args.omr_sample_limit,
                    "--random-seed",
                    args.random_seed,
                )
            )
    if args.run_omr:
        outputs_root = args.reports_dir.parent
        sample_path = args.labels_dir / "omr_eval_sample_thesis.csv"
        omr_pages = outputs_root / "omr_pages"
        omr_output = outputs_root / "omr_300dpi"
        commands["run_omr"].extend(
            [
                _script_command(
                    "extract_omr_pages.py",
                    "--candidates",
                    sample_path,
                    "--raw-dir",
                    args.raw_dir,
                    "--out-dir",
                    omr_pages,
                    "--dpi",
                    300,
                    "--limit",
                    args.omr_sample_limit,
                ),
                _script_command(
                    "run_audiveris_omr.py",
                    "--candidates",
                    sample_path,
                    "--omr-pages-dir",
                    omr_pages,
                    "--out-dir",
                    omr_output,
                    "--limit",
                    args.omr_sample_limit,
                    "--audiveris-bin",
                    args.audiveris_bin,
                    "--resume",
                ),
            ]
        )
    return commands


def find_document_dirs(
    raw_dir: Path,
    *,
    doc_id: str | None = None,
    limit_docs: int | None = None,
) -> list[Path]:
    """Find deterministic document directories for page processing."""
    if not raw_dir.is_dir():
        return []
    directories = sorted(
        (path for path in raw_dir.iterdir() if path.is_dir()),
        key=lambda path: path.name,
    )
    if doc_id:
        directories = [path for path in directories if path.name == doc_id]
    if limit_docs is not None:
        directories = directories[:limit_docs]
    return directories


def build_document_commands(
    document_dirs: Sequence[Path],
    args: argparse.Namespace,
) -> tuple[list[list[str]], list[list[str]]]:
    """Build extraction and detector commands for selected documents."""
    predictions_dir = args.reports_dir.parent / "predictions"
    extraction: list[list[str]] = []
    detection: list[list[str]] = []
    for document_dir in document_dirs:
        doc_id = document_dir.name
        page_dir = args.pages_dir / doc_id
        manifest = page_dir / "manifest.csv"
        prediction = predictions_dir / f"{doc_id}_page_predictions.csv"
        extraction.append(
            _script_command(
                "extract_pages.py",
                "--document-dir",
                document_dir,
                "--out",
                page_dir,
                "--doc-id",
                doc_id,
                "--dpi",
                args.dpi,
            )
        )
        detection.append(
            _script_command(
                "run_pipeline.py",
                "--manifest",
                manifest,
                "--out",
                prediction,
            )
        )
    return extraction, detection


def _command_output_path(command: Sequence[str], flag: str) -> Path | None:
    try:
        return Path(command[command.index(flag) + 1])
    except (ValueError, IndexError):
        return None


def should_skip(command: Sequence[str], stage: str, args: argparse.Namespace) -> bool:
    """Return whether resume/skip-existing can safely skip this command."""
    if not (args.resume or args.skip_existing):
        return False
    if stage == "extracting":
        output_dir = _command_output_path(command, "--out")
        return bool(output_dir and (output_dir / "manifest.csv").is_file())
    if stage == "detector":
        output_path = _command_output_path(command, "--out")
        return bool(output_path and output_path.is_file())
    return False


def default_runner(command: Sequence[str]) -> CommandResult:
    completed = subprocess.run(
        list(command),
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return CommandResult(
        command=list(command),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _command_text(command: Sequence[str]) -> str:
    return subprocess.list2cmdline([str(part) for part in command])


def execute_commands(
    stage: str,
    commands: Sequence[Sequence[str]],
    args: argparse.Namespace,
    logs: list[dict[str, object]],
    *,
    runner: Callable[[Sequence[str]], CommandResult] = default_runner,
) -> bool:
    """Execute one stage and return False when fail-fast should stop."""
    for command in commands:
        script_path = Path(command[1]) if len(command) > 1 else None
        if script_path is not None and not script_path.is_file():
            result = CommandResult(
                command=list(command),
                returncode=2,
                stderr=f"Required script does not exist: {script_path}",
            )
            runtime = 0.0
        elif args.dry_run:
            planned_status = (
                "WOULD SKIP"
                if should_skip(command, stage, args)
                else "DRY-RUN"
            )
            print(f"  {planned_status}: {_command_text(command)}")
            logs.append(
                {
                    "stage": stage,
                    "command": _command_text(command),
                    "status": "planned",
                    "returncode": "",
                    "runtime_seconds": 0.0,
                    "message": (
                        "Existing output would be retained."
                        if planned_status == "WOULD SKIP"
                        else ""
                    ),
                }
            )
            continue
        elif should_skip(command, stage, args):
            logs.append(
                {
                    "stage": stage,
                    "command": _command_text(command),
                    "status": "skipped",
                    "returncode": 0,
                    "runtime_seconds": 0.0,
                    "message": "Existing output retained by resume/skip-existing.",
                }
            )
            continue
        else:
            started = time.perf_counter()
            result = runner(command)
            runtime = time.perf_counter() - started

        status = "success" if result.returncode == 0 else "error"
        message = (result.stderr or result.stdout).strip()
        logs.append(
            {
                "stage": stage,
                "command": _command_text(command),
                "status": status,
                "returncode": result.returncode,
                "runtime_seconds": round(runtime, 6),
                "message": message,
            }
        )
        if result.returncode != 0:
            print(f"  ERROR: stage '{stage}' failed.")
            print(f"  Command: {_command_text(command)}")
            print(f"  Check: {message or 'script inputs and dependencies'}")
            if args.fail_fast:
                return False
    return True


def combine_prediction_files(predictions_dir: Path, output_path: Path) -> int:
    """Combine existing per-document predictions using their CSV contract."""
    files = sorted(predictions_dir.glob("*_page_predictions.csv"))
    fieldnames: list[str] = []
    rows: list[dict[str, str]] = []
    for path in files:
        with path.open(encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            if not fieldnames:
                fieldnames = list(reader.fieldnames or [])
            rows.extend(reader)
    if not fieldnames:
        fieldnames = [
            "doc_id",
            "page_index",
            "image_path",
            "has_music_pred",
            "has_music_score",
            "black_pixel_ratio",
            "horizontal_line_count",
            "horizontal_line_density",
            "staff_like_line_groups",
        ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def collect_summary(args: argparse.Namespace, logs: list[dict[str, object]]) -> dict[str, object]:
    inventory = _read_rows(args.labels_dir / "document_inventory.csv")
    statistics_rows = _read_rows(args.reports_dir / "dataset_statistics.csv")
    statistics = statistics_rows[0] if statistics_rows else {}
    return {
        "documents": len(inventory),
        "pdf_exists": sum(row.get("pdf_status") == "exists" for row in inventory),
        "mrc_parsed": sum(row.get("mrc_status") == "parsed" for row in inventory),
        "total_pages": int(float(statistics.get("total_pages", 0) or 0)),
        "page_types": {
            page_type: int(float(statistics.get(page_type, 0) or 0))
            for page_type in PAGE_TYPES
        },
        "errors": sum(row["status"] == "error" for row in logs),
    }


def write_run_reports(
    args: argparse.Namespace,
    logs: list[dict[str, object]],
    summary: dict[str, object],
) -> tuple[Path, Path]:
    log_path = args.reports_dir / "corpus_analysis_run_log.csv"
    summary_path = args.reports_dir / "corpus_analysis_run_summary.md"
    args.reports_dir.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=LOG_COLUMNS)
        writer.writeheader()
        writer.writerows(logs)
    page_rows = "\n".join(
        f"| `{page_type}` | {summary['page_types'][page_type]} |"
        for page_type in PAGE_TYPES
    )
    summary_path.write_text(
        f"""# Corpus analysis run summary

| Показатель | Значение |
|---|---:|
| Документов в inventory | {summary['documents']} |
| PDF exists | {summary['pdf_exists']} |
| MRC parsed | {summary['mrc_parsed']} |
| Страниц всего | {summary['total_pages']} |
| Ошибок этапов | {summary['errors']} |

## Типы страниц

| page_type | Количество |
|---|---:|
{page_rows}

## Основные результаты

- Inventory: `{(args.labels_dir / 'document_inventory.csv').as_posix()}`
- Predictions: `{(args.reports_dir / 'all_page_predictions.csv').as_posix()}`
- Labels template: `{(args.labels_dir / 'pages_template_thesis.csv').as_posix()}`
- Dataset statistics: `{(args.reports_dir / 'dataset_statistics.csv').as_posix()}`
- Run log: `{log_path.as_posix()}`

OMR не является частью стандартного запуска. Он выполняется только при явном
флаге `--run-omr`.
""",
        encoding="utf-8",
    )
    return log_path, summary_path


def run_corpus_analysis(
    args: argparse.Namespace,
    *,
    runner: Callable[[Sequence[str]], CommandResult] = default_runner,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Run the orchestrated workflow and return execution logs plus summary."""
    static = build_static_commands(args)
    logs: list[dict[str, object]] = []
    stages = [
        ("organize", "Organizing inbox", static["organize"]),
        ("inventory", "Building document inventory", static["inventory"]),
    ]
    for index, (key, label, commands) in enumerate(stages, start=1):
        print(f"[{index}/7] {label}")
        if not execute_commands(key, commands, args, logs, runner=runner):
            summary = collect_summary(args, logs)
            if not args.dry_run:
                write_run_reports(args, logs, summary)
            return logs, summary

    document_dirs = find_document_dirs(
        args.raw_dir,
        doc_id=args.doc_id,
        limit_docs=args.limit_docs,
    )
    extraction, detection = build_document_commands(document_dirs, args)
    dynamic_stages = [
        ("extracting", "Extracting pages", extraction),
        ("detector", "Running detector", detection),
    ]
    for offset, (key, label, commands) in enumerate(dynamic_stages, start=3):
        print(f"[{offset}/7] {label}")
        if not execute_commands(key, commands, args, logs, runner=runner):
            summary = collect_summary(args, logs)
            if not args.dry_run:
                write_run_reports(args, logs, summary)
            return logs, summary

    print("[5/7] Building labels template")
    if not args.dry_run:
        try:
            combine_prediction_files(
                args.reports_dir.parent / "predictions",
                args.reports_dir / "all_page_predictions.csv",
            )
        except Exception as error:
            logs.append(
                {
                    "stage": "labels",
                    "command": "combine prediction CSV files",
                    "status": "error",
                    "returncode": 1,
                    "runtime_seconds": 0.0,
                    "message": str(error),
                }
            )
            if args.fail_fast:
                summary = collect_summary(args, logs)
                write_run_reports(args, logs, summary)
                return logs, summary
    else:
        print("  DRY-RUN: combine outputs/predictions/*_page_predictions.csv")
    if not execute_commands("labels", static["labels"], args, logs, runner=runner):
        summary = collect_summary(args, logs)
        if not args.dry_run:
            write_run_reports(args, logs, summary)
        return logs, summary

    print("[6/7] Building dataset statistics")
    if not execute_commands(
        "statistics", static["statistics"], args, logs, runner=runner
    ):
        summary = collect_summary(args, logs)
        if not args.dry_run:
            write_run_reports(args, logs, summary)
        return logs, summary

    print("[7/7] Building detector reports")
    execute_commands("reports", static["reports"], args, logs, runner=runner)

    if args.prepare_omr_sample or args.run_omr:
        print("[OMR] Preparing OMR sample")
        if not static["prepare_omr"]:
            print("  TODO: build_omr_eval_sample.py is not available.")
        elif not execute_commands(
            "prepare_omr", static["prepare_omr"], args, logs, runner=runner
        ):
            summary = collect_summary(args, logs)
            if not args.dry_run:
                write_run_reports(args, logs, summary)
            return logs, summary
    if args.run_omr:
        print("[OMR] Running separate OMR workflow")
        execute_commands("run_omr", static["run_omr"], args, logs, runner=runner)

    summary = collect_summary(args, logs)
    if not args.dry_run:
        write_run_reports(args, logs, summary)
    return logs, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inbox", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--pages-dir", type=Path, required=True)
    parser.add_argument("--labels-dir", type=Path, required=True)
    parser.add_argument("--reports-dir", type=Path, required=True)
    parser.add_argument("--docs-dir", type=Path, required=True)
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--limit-docs", type=int)
    parser.add_argument("--doc-id")
    parser.add_argument("--dry-run", action="store_true")
    behavior = parser.add_mutually_exclusive_group()
    behavior.add_argument("--fail-fast", action="store_true")
    behavior.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--prepare-omr-sample", action="store_true")
    parser.add_argument("--run-omr", action="store_true")
    parser.add_argument("--omr-sample-limit", type=int, default=150)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--audiveris-bin", default="audiveris")
    args = parser.parse_args()
    if args.limit_docs is not None and args.limit_docs <= 0:
        parser.error("--limit-docs must be positive")
    if args.dpi <= 0:
        parser.error("--dpi must be positive")
    return args


def main() -> None:
    args = parse_args()
    logs, summary = run_corpus_analysis(args)
    print("")
    print("Corpus analysis summary")
    print(f"Documents in inventory: {summary['documents']}")
    print(f"PDF exists: {summary['pdf_exists']}")
    print(f"MRC parsed: {summary['mrc_parsed']}")
    print(f"Total pages: {summary['total_pages']}")
    for page_type in PAGE_TYPES:
        print(f"{page_type}: {summary['page_types'][page_type]}")
    print(f"Errors: {summary['errors']}")
    if args.dry_run:
        print("Dry-run completed; no files were created.")
    else:
        print(f"Run log: {args.reports_dir / 'corpus_analysis_run_log.csv'}")
        print(
            "Run summary: "
            f"{args.reports_dir / 'corpus_analysis_run_summary.md'}"
        )
    if summary["errors"] and args.fail_fast:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
