"""Safe small parallel OMR batch runner.

The runner is intentionally conservative: default mode is dry-run, maximum
pages are limited, and all outputs are written to separate target folders.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from datetime import datetime
from pathlib import Path
from shutil import copy2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
for import_path in (SRC_DIR, SCRIPTS_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from analyze_music_features_unique_pages import (  # noqa: E402
    DEFAULT_ROOTS,
    DEFAULT_VALIDATED,
    find_artifacts,
    page_key,
    pct,
    read_validated_pages,
)
from notevision.music_features import extract_music_features  # noqa: E402

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "omr_batch_parallel_test"
DEFAULT_MIDI_DIR = PROJECT_ROOT / "outputs" / "midi_batch_parallel_test"
DEFAULT_REPORT = PROJECT_ROOT / "outputs" / "reports" / "omr_batch_parallel_test_report.md"
DEFAULT_RAW = PROJECT_ROOT / "outputs" / "reports" / "omr_batch_parallel_test_raw.csv"

EXPERIMENTAL_OUTPUT_MARKERS = {
    "omr_timing_sample",
    "midi_timing_sample",
    "omr_batch_parallel_test",
    "midi_batch_parallel_test",
}

RAW_COLUMNS = [
    "run_label",
    "doc_id",
    "page_index",
    "page_type",
    "png_path",
    "status",
    "skip_reason",
    "worker_id",
    "page_preprocessing_ms",
    "audiveris_omr_ms",
    "mxl_created",
    "mxl_path",
    "midi_conversion_ms",
    "midi_created",
    "midi_path",
    "music_features_extraction_ms",
    "features_extracted",
    "total_ms",
    "error",
]


def rel(path: Path | str) -> str:
    path_obj = Path(path)
    try:
        return str(path_obj.resolve().relative_to(PROJECT_ROOT))
    except (OSError, ValueError):
        return str(path)


def resolve_project_path(value: object) -> Path:
    raw = str(value or "").strip().replace("\\", "/")
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def write_csv(path: Path, rows: list[dict[str, object]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def existing_artifact_index(roots: list[Path]) -> dict[tuple[str, str], list[Path]]:
    index: dict[tuple[str, str], list[Path]] = {}
    for artifact in find_artifacts(roots):
        normalized = str(artifact.path).replace("\\", "/").lower()
        if any(marker in normalized for marker in EXPERIMENTAL_OUTPUT_MARKERS):
            continue
        if artifact.doc_id != "unknown" and artifact.page_index != "unknown":
            index.setdefault((artifact.doc_id, artifact.page_index), []).append(artifact.path)
    return index


def target_mxl(output_dir: Path, doc_id: str, page_index: str) -> Path | None:
    try:
        page_dir = output_dir / doc_id / f"page_{int(float(page_index)):03d}"
    except ValueError:
        return None
    if not page_dir.is_dir():
        return None
    files = sorted(page_dir.rglob("*.mxl"), key=lambda path: str(path).lower())
    return files[0] if files else None


def select_pages(
    validated_rows: list[dict[str, str]],
    existing_index: dict[tuple[str, str], list[Path]],
    *,
    page_types: set[str],
    only_without_mxl: bool,
    max_pages: int,
    output_dir: Path,
) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    for row in validated_rows:
        page_type = str(row.get("page_type", "")).strip().lower()
        if page_type not in page_types:
            continue
        doc_id, page_index = page_key(str(row.get("doc_id", "")).strip(), row.get("page_index", ""))
        png_path = resolve_project_path(row.get("image_path", ""))
        if not png_path.is_file():
            continue
        existing_mxl = bool(existing_index.get((doc_id, page_index)))
        if only_without_mxl and existing_mxl:
            continue
        if target_mxl(output_dir, doc_id, page_index) is not None:
            continue
        selected.append(
            {
                "doc_id": doc_id,
                "page_index": page_index,
                "page_type": page_type,
                "png_path": rel(png_path),
                "existing_mxl_found": int(existing_mxl),
                "selected_for_run": 1,
            }
        )
        if len(selected) >= max_pages:
            break
    return selected


def preprocess_page(source_png: Path, work_png: Path) -> float:
    start = time.perf_counter()
    work_png.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image

        with Image.open(source_png) as image:
            image.convert("L").save(work_png)
    except Exception:
        copy2(source_png, work_png)
    return (time.perf_counter() - start) * 1000.0


def build_audiveris_command(input_path: Path, out_dir: Path, audiveris_bin: str) -> list[str]:
    return [audiveris_bin, "-batch", "-transcribe", "-export", "-output", str(out_dir), "--", str(input_path)]


def find_created_mxl(out_dir: Path, input_path: Path) -> Path | None:
    candidates = list(out_dir.rglob(f"{input_path.stem}*.mxl"))
    if not candidates:
        candidates = list(out_dir.rglob("*.mxl"))
    files = sorted((path for path in candidates if path.is_file()), key=lambda path: str(path).lower())
    return files[0] if files else None


def run_audiveris(input_path: Path, out_dir: Path, audiveris_bin: str) -> tuple[float, Path | None, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / f"{input_path.stem}_audiveris.log"
    command = build_audiveris_command(input_path, out_dir, audiveris_bin)
    start = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError:
        duration_ms = (time.perf_counter() - start) * 1000.0
        message = f"Audiveris executable was not found: {audiveris_bin}"
        log_path.write_text(message + "\n", encoding="utf-8")
        return duration_ms, None, message
    except OSError as error:
        duration_ms = (time.perf_counter() - start) * 1000.0
        message = f"Could not start Audiveris: {error}"
        log_path.write_text(message + "\n", encoding="utf-8")
        return duration_ms, None, message
    duration_ms = (time.perf_counter() - start) * 1000.0
    log_path.write_text(
        "\n".join(
            [
                f"Command: {subprocess.list2cmdline(command)}",
                f"Return code: {completed.returncode}",
                "",
                "STDOUT",
                completed.stdout or "",
                "",
                "STDERR",
                completed.stderr or "",
                "",
            ]
        ),
        encoding="utf-8",
    )
    if completed.returncode != 0:
        return duration_ms, None, f"Audiveris exited with code {completed.returncode}; log={rel(log_path)}"
    return duration_ms, find_created_mxl(out_dir, input_path), ""


def convert_mxl_to_midi(source_mxl: Path, midi_path: Path) -> tuple[float, bool, str]:
    start = time.perf_counter()
    try:
        from music21 import bar, converter, repeat

        midi_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            score = converter.parse(str(source_mxl))
            score.write("midi", fp=str(midi_path))
        except repeat.ExpanderException:
            score = converter.parse(str(source_mxl))
            for measure in score.recurse().getElementsByClass("Measure"):
                if isinstance(measure.leftBarline, bar.Repeat):
                    measure.leftBarline = None
                if isinstance(measure.rightBarline, bar.Repeat):
                    measure.rightBarline = None
            score.write("midi", fp=str(midi_path))
        return (time.perf_counter() - start) * 1000.0, midi_path.is_file(), ""
    except Exception as error:
        return (time.perf_counter() - start) * 1000.0, False, f"MIDI conversion failed: {error}"


def extract_features(source_mxl: Path) -> tuple[float, bool, str]:
    start = time.perf_counter()
    try:
        row = extract_music_features(source_mxl)
        status = str(row.get("extraction_status", ""))
        return (time.perf_counter() - start) * 1000.0, status not in {"parse_error", "missing_file"}, str(row.get("error", "") or "")
    except Exception as error:
        return (time.perf_counter() - start) * 1000.0, False, f"Music features extraction failed: {error}"


def process_page(page: dict[str, object], args: argparse.Namespace, worker_id: int) -> dict[str, object]:
    doc_id = str(page["doc_id"])
    page_index = str(page["page_index"])
    page_name = f"page_{int(float(page_index)):03d}"
    source_png = resolve_project_path(page["png_path"])
    page_out_dir = args.output_dir / doc_id / page_name
    existing_target_mxl = target_mxl(args.output_dir, doc_id, page_index)
    if existing_target_mxl is not None:
        return base_row(page, args.run_label, worker_id, "skipped", "target_mxl_exists", mxl_path=existing_target_mxl)

    work_png = page_out_dir / f"{page_name}_parallel_input.png"
    midi_path = args.midi_output_dir / doc_id / f"{page_name}.mid"
    total_start = time.perf_counter()
    errors: list[str] = []
    preprocessing_ms = preprocess_page(source_png, work_png)
    audiveris_ms, mxl_path, audiveris_error = run_audiveris(work_png, page_out_dir, args.audiveris_bin)
    if audiveris_error:
        errors.append(audiveris_error)

    midi_ms = 0.0
    midi_created = False
    features_ms = 0.0
    features_extracted = False
    if mxl_path is not None and mxl_path.is_file():
        midi_ms, midi_created, midi_error = convert_mxl_to_midi(mxl_path, midi_path)
        if midi_error:
            errors.append(midi_error)
        features_ms, features_extracted, features_error = extract_features(mxl_path)
        if features_error:
            errors.append(features_error)

    status = "success" if mxl_path is not None and mxl_path.is_file() else "failed"
    row = base_row(page, args.run_label, worker_id, status, "")
    row.update(
        {
            "page_preprocessing_ms": round(preprocessing_ms, 3),
            "audiveris_omr_ms": round(audiveris_ms, 3),
            "mxl_created": int(mxl_path is not None and mxl_path.is_file()),
            "mxl_path": rel(mxl_path) if mxl_path else "",
            "midi_conversion_ms": round(midi_ms, 3),
            "midi_created": int(midi_created),
            "midi_path": rel(midi_path) if midi_created else "",
            "music_features_extraction_ms": round(features_ms, 3),
            "features_extracted": int(features_extracted),
            "total_ms": round((time.perf_counter() - total_start) * 1000.0, 3),
            "error": " | ".join(errors),
        }
    )
    return row


def base_row(
    page: dict[str, object],
    run_label: str,
    worker_id: int,
    status: str,
    skip_reason: str,
    *,
    mxl_path: Path | None = None,
) -> dict[str, object]:
    return {
        "run_label": run_label,
        "doc_id": page["doc_id"],
        "page_index": page["page_index"],
        "page_type": page["page_type"],
        "png_path": page["png_path"],
        "status": status,
        "skip_reason": skip_reason,
        "worker_id": worker_id,
        "page_preprocessing_ms": 0.0,
        "audiveris_omr_ms": 0.0,
        "mxl_created": int(mxl_path is not None),
        "mxl_path": rel(mxl_path) if mxl_path else "",
        "midi_conversion_ms": 0.0,
        "midi_created": 0,
        "midi_path": "",
        "music_features_extraction_ms": 0.0,
        "features_extracted": 0,
        "total_ms": 0.0,
        "error": "",
    }


def run_pages(pages: list[dict[str, object]], args: argparse.Namespace) -> tuple[list[dict[str, object]], float]:
    if args.dry_run:
        rows = [base_row(page, args.run_label, 0, "dry_run", "") for page in pages]
        return rows, 0.0
    start = time.perf_counter()
    rows: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_index = {
            executor.submit(process_page, page, args, (index % args.workers) + 1): index
            for index, page in enumerate(pages)
        }
        for future in as_completed(future_to_index):
            try:
                rows.append(future.result())
            except Exception as error:
                page = pages[future_to_index[future]]
                row = base_row(page, args.run_label, 0, "failed", "")
                row["error"] = f"Unhandled page error: {error}"
                rows.append(row)
    rows.sort(key=lambda row: (str(row["doc_id"]), int(float(str(row["page_index"])))))
    return rows, (time.perf_counter() - start) * 1000.0


def stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "median": 0.0, "min": 0.0, "max": 0.0}
    return {
        "mean": round(statistics.fmean(values), 3),
        "median": round(statistics.median(values), 3),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
    }


def summarize(rows: list[dict[str, object]], wall_ms: float, workers: int) -> dict[str, object]:
    processed = [row for row in rows if str(row["status"]) not in {"dry_run", "skipped"}]
    success = [row for row in processed if str(row["status"]) == "success"]
    return {
        "workers": workers,
        "selected_pages": len(rows),
        "processed_pages": len(processed),
        "success_pages": len(success),
        "failed_pages": sum(1 for row in processed if str(row["status"]) == "failed"),
        "skipped_pages": sum(1 for row in rows if str(row["status"]) == "skipped"),
        "mxl_created": sum(int(row["mxl_created"]) for row in rows),
        "midi_created": sum(int(row["midi_created"]) for row in rows),
        "features_extracted": sum(int(row["features_extracted"]) for row in rows),
        "wall_seconds": round(wall_ms / 1000.0, 3),
        "preprocessing": stats([float(row["page_preprocessing_ms"]) for row in processed if float(row["page_preprocessing_ms"]) > 0]),
        "audiveris": stats([float(row["audiveris_omr_ms"]) for row in processed if float(row["audiveris_omr_ms"]) > 0]),
        "midi": stats([float(row["midi_conversion_ms"]) for row in processed if float(row["midi_conversion_ms"]) > 0]),
        "features": stats([float(row["music_features_extraction_ms"]) for row in processed if float(row["music_features_extraction_ms"]) > 0]),
        "total": stats([float(row["total_ms"]) for row in processed if float(row["total_ms"]) > 0]),
        "statuses": Counter(str(row["status"]) for row in rows),
    }


def write_report(path: Path, rows: list[dict[str, object]], summary: dict[str, object], args: argparse.Namespace) -> None:
    lines = [
        "# OMR parallel batch test report",
        "",
        f"- Run timestamp: {datetime.now().isoformat(timespec='seconds')}",
        f"- Run label: {args.run_label}",
        f"- Mode: {'dry-run' if args.dry_run else 'run'}",
        f"- Workers: {summary['workers']}",
        f"- Max pages: {args.max_pages}",
        "- Output is isolated from OMR-300/fallback folders.",
        "",
        "## Summary",
        "",
        f"- Selected pages: {summary['selected_pages']}.",
        f"- Processed pages: {summary['processed_pages']}.",
        f"- Success pages / MXL created: {summary['mxl_created']}.",
        f"- MIDI created: {summary['midi_created']}.",
        f"- Music features extracted: {summary['features_extracted']}.",
        f"- Failed pages: {summary['failed_pages']}.",
        f"- Wall time: {summary['wall_seconds']} s.",
        "",
        "## Timing",
        "",
        "| stage | mean_ms | median_ms | min_ms | max_ms |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, key in (
        ("Page preprocessing", "preprocessing"),
        ("Audiveris OMR", "audiveris"),
        ("MIDI conversion", "midi"),
        ("Music features extraction", "features"),
        ("Total per page", "total"),
    ):
        values = summary[key]
        lines.append(f"| {label} | {values['mean']} | {values['median']} | {values['min']} | {values['max']} |")
    lines.extend(
        [
            "",
            "## Per-page statuses",
            "",
            "| doc_id | page_index | status | mxl_created | midi_created | features_extracted | total_ms | error |",
            "|---|---:|---|---:|---:|---:|---:|---|",
        ]
    )
    for row in rows:
        error = str(row["error"]).replace("|", "/")
        lines.append(
            f"| {row['doc_id']} | {row['page_index']} | {row['status']} | {row['mxl_created']} | {row['midi_created']} | {row['features_extracted']} | {row['total_ms']} | {error} |"
        )
    lines.extend(
        [
            "",
            "## Defense wording",
            "",
            "> The main computational stage is Audiveris. Speedup is possible not by accelerating music-feature extraction, but by avoiding unnecessary OMR pages, caching existing MXL/MIDI artifacts, and running independent pages in parallel. Full corpus batch processing is separate from final VKR metrics.",
            "",
            "## Limitations",
            "",
            "- This small run does not prove production readiness of parallel mode.",
            "- This is not OMR accuracy and not musical correctness.",
            "- This does not change final VKR metrics.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validated", type=Path, default=DEFAULT_VALIDATED)
    parser.add_argument("--page-types", default="music,mixed")
    parser.add_argument("--only-without-mxl", action="store_true")
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--midi-output-dir", type=Path, default=DEFAULT_MIDI_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--raw-output", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--audiveris-bin", default="audiveris")
    parser.add_argument("--run-label", default="parallel_test")
    parser.add_argument("--roots", type=Path, nargs="*", default=DEFAULT_ROOTS)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    args.dry_run = not args.run
    if args.max_pages <= 0 or args.max_pages > 100:
        raise SystemExit("--max-pages must be between 1 and 100")
    if args.workers <= 0 or args.workers > 4:
        raise SystemExit("--workers must be between 1 and 4")
    forbidden = {"omr_eval_300", "omr_300dpi", "omr_400dpi_fallback", "omr_preprocessed_fallback"}
    output_text = str(args.output_dir).replace("\\", "/").lower()
    midi_text = str(args.midi_output_dir).replace("\\", "/").lower()
    if any(name in output_text or name in midi_text for name in forbidden):
        raise SystemExit("Refusing to write into OMR-300/fallback output folders")


def main() -> int:
    args = parse_args()
    validate_args(args)
    page_types = {item.strip().lower() for item in args.page_types.split(",") if item.strip()}
    existing_index = existing_artifact_index(list(args.roots))
    selected = select_pages(
        read_validated_pages(args.validated),
        existing_index,
        page_types=page_types,
        only_without_mxl=args.only_without_mxl,
        max_pages=args.max_pages,
        output_dir=args.output_dir,
    )
    rows, wall_ms = run_pages(selected, args)
    summary = summarize(rows, wall_ms, args.workers)
    write_csv(args.raw_output, rows, RAW_COLUMNS)
    write_report(args.report, rows, summary, args)
    print(f"Mode: {'dry-run' if args.dry_run else 'run'}")
    print(f"Workers: {args.workers}")
    print(f"Selected pages: {summary['selected_pages']}")
    print(f"Processed pages: {summary['processed_pages']}")
    print(f"MXL/MIDI/features: {summary['mxl_created']}/{summary['midi_created']}/{summary['features_extracted']}")
    print(f"Failures: {summary['failed_pages']}")
    print(f"Wall seconds: {summary['wall_seconds']}")
    print(f"Report: {args.report}")
    print(f"Raw CSV: {args.raw_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
