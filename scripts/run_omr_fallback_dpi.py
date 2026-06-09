"""Retry failed 300 DPI OMR pages at a separate fallback DPI."""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

DEFAULT_FAILURE_REPORT = PROJECT_ROOT / "outputs" / "reports" / "omr_failure_report.csv"
DEFAULT_REPORT = PROJECT_ROOT / "outputs" / "reports" / "omr_400dpi_fallback_report.csv"
DEFAULT_SUMMARY = PROJECT_ROOT / "outputs" / "reports" / "omr_400dpi_fallback_summary.md"

REPORT_COLUMNS = (
    "doc_id",
    "page_index",
    "primary_failure_status",
    "fallback_400_status",
    "fallback_400_mxl_path",
    "fallback_400_midi_path",
    "fallback_400_runtime_seconds",
    "fallback_400_error",
    "run_action",
)
FAILURE_STATUSES = {"failed", "missing_mxl", "no_mxl", "no mxl"}


def find_existing_mxl(
    output_dir: Path,
    *,
    input_path: Path | None = None,
    page_index: int | None = None,
) -> Path | None:
    """Find an MXL export without importing the pandas-based batch runner."""
    if not output_dir.is_dir():
        return None
    patterns = ["*.mxl"]
    if page_index is not None:
        patterns.insert(0, f"page_{page_index:03d}*.mxl")
    if input_path is not None:
        patterns.insert(0, f"{input_path.stem}*.mxl")
    candidates = {
        path
        for pattern in patterns
        for path in output_dir.glob(pattern)
        if path.is_file()
    }
    return sorted(candidates, key=lambda path: str(path).lower())[0] if candidates else None


def default_audiveris_runner(
    input_path: Path,
    output_dir: Path,
    *,
    audiveris_bin: str,
) -> dict[str, object]:
    from notevision.omr.audiveris import run_audiveris

    return run_audiveris(
        input_path,
        output_dir,
        audiveris_bin=audiveris_bin,
    )


def default_midi_converter(
    source_mxl: Path,
    midi_path: Path,
) -> dict[str, str]:
    from scripts.convert_mxl_to_midi import convert_mxl_to_midi

    return convert_mxl_to_midi(source_mxl, midi_path)


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        raise FileNotFoundError(f"OMR report does not exist: {path}")
    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        return list(reader.fieldnames or []), list(reader)


def _page_key(row: dict[str, str]) -> tuple[str, int]:
    doc_id = str(row.get("doc_id", "")).strip()
    try:
        page_index = int(float(str(row.get("page_index", "")).strip()))
    except ValueError as error:
        raise ValueError(f"Invalid page_index for {doc_id or '<empty>'}") from error
    if not doc_id or page_index < 1:
        raise ValueError("Failure rows require doc_id and positive page_index")
    return doc_id, page_index


def _failure_status(row: dict[str, str]) -> str:
    status = str(
        row.get("failure_type")
        or row.get("failure_status")
        or row.get("status")
        or ""
    ).strip().lower()
    has_mxl = str(row.get("has_mxl", "")).strip().lower()
    if not status and has_mxl in {"false", "0", "no"}:
        return "missing_mxl"
    return status


def select_failed_pages(
    omr_report: Path,
    *,
    failure_report: Path | None = None,
    doc_id: str | None = None,
    page_index: int | None = None,
    limit: int | None = None,
) -> tuple[list[dict[str, object]], dict[str, int | None]]:
    """Select page-level missing-MXL rows and retain primary sample totals."""
    fields, rows = _read_csv(omr_report)
    sample_total: int | None = None
    total_failures: int | None = None
    if {"sampled_pages", "mxl_generated_pages"}.issubset(fields):
        sample_total = sum(int(float(row["sampled_pages"])) for row in rows)
        primary_mxl = sum(int(float(row["mxl_generated_pages"])) for row in rows)
        total_failures = sample_total - primary_mxl
        page_report = failure_report or omr_report.with_name("omr_failure_report.csv")
        fields, rows = _read_csv(page_report)

    if not {"doc_id", "page_index"}.issubset(fields):
        raise ValueError(
            "A page-level failure report with doc_id,page_index is required."
        )
    selected: dict[tuple[str, int], dict[str, object]] = {}
    for row in rows:
        status = _failure_status(row)
        if status not in FAILURE_STATUSES:
            continue
        key = _page_key(row)
        if doc_id and key[0] != doc_id:
            continue
        if page_index is not None and key[1] != page_index:
            continue
        selected[key] = {
            "doc_id": key[0],
            "page_index": key[1],
            "image_path": str(row.get("image_path", "")).strip(),
            "primary_failure_status": status,
        }
    pages = [selected[key] for key in sorted(selected)]
    if total_failures is None:
        total_failures = len(pages)
    if limit is not None:
        if limit <= 0:
            raise ValueError("limit must be a positive integer")
        pages = pages[:limit]
    return pages, {
        "sample_total": sample_total,
        "total_300dpi_failures": total_failures,
    }


def extract_pdf_page(
    raw_dir: Path,
    doc_id: str,
    page_index: int,
    output_path: Path,
    dpi: int,
) -> None:
    """Extract one source-PDF page at the requested fallback DPI."""
    import pymupdf
    from notevision.pdf.extract_pages import find_pdf_in_document_dir

    pdf_path = find_pdf_in_document_dir(raw_dir / doc_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(str(pdf_path)) as document:
        if page_index < 1 or page_index > len(document):
            raise IndexError(
                f"Page {page_index} is outside PDF range 1..{len(document)}"
            )
        document[page_index - 1].get_pixmap(dpi=dpi, alpha=False).save(
            str(output_path)
        )


def _find_midi(midi_dir: Path, doc_id: str, page_index: int) -> Path | None:
    for extension in (".mid", ".midi"):
        candidate = midi_dir / doc_id / f"page_{page_index:03d}{extension}"
        if candidate.is_file():
            return candidate
    return None


def _relative(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def run_fallback_pages(
    pages: list[dict[str, object]],
    *,
    raw_dir: Path,
    pages_dir: Path,
    out_dir: Path,
    midi_dir: Path,
    dpi: int = 400,
    skip_existing: bool = True,
    resume: bool = False,
    audiveris_bin: str = "audiveris",
    extractor: Callable[[Path, str, int, Path, int], None] = extract_pdf_page,
    audiveris_runner: Callable[..., dict[str, object]] = default_audiveris_runner,
    midi_converter: Callable[[Path, Path], dict[str, str]] = default_midi_converter,
    clock: Callable[[], float] = time.perf_counter,
) -> list[dict[str, object]]:
    """Extract, retry Audiveris, and convert recovered MXL files to MIDI."""
    if dpi <= 0:
        raise ValueError("dpi must be a positive integer")
    rows: list[dict[str, object]] = []
    for page in pages:
        started = clock()
        doc_id = str(page["doc_id"])
        page_index = int(page["page_index"])
        page_dir = out_dir / doc_id / f"page_{page_index:03d}"
        input_path = page_dir / f"page_{page_index:03d}_{dpi}dpi.png"
        midi_path = midi_dir / doc_id / f"page_{page_index:03d}.mid"
        found_mxl = find_existing_mxl(
            page_dir,
            input_path=input_path,
            page_index=page_index,
        )
        found_midi = _find_midi(midi_dir, doc_id, page_index)
        existing_mxl = found_mxl if (skip_existing or resume) else None
        existing_midi = found_midi if (skip_existing or resume) else None
        error = ""
        action = "resumed" if resume else "processed"

        if existing_mxl is not None and existing_midi is not None and (
            skip_existing or resume
        ):
            status = "recovered_midi"
            mxl_path = existing_mxl
            midi_result_path = existing_midi
            action = "skipped"
        else:
            mxl_path = existing_mxl
            midi_result_path = existing_midi
            try:
                if mxl_path is None:
                    if not input_path.is_file():
                        extractor(raw_dir, doc_id, page_index, input_path, dpi)
                    result = audiveris_runner(
                        input_path,
                        page_dir,
                        audiveris_bin=audiveris_bin,
                    )
                    action = "resumed" if resume else "processed"
                    if result.get("status") != "success":
                        raise RuntimeError(str(result.get("message") or "Audiveris failed"))
                    mxl_path = find_existing_mxl(
                        page_dir,
                        input_path=input_path,
                        page_index=page_index,
                    )
                    if mxl_path is None:
                        raise RuntimeError("Audiveris finished without an MXL export")

                if midi_result_path is None:
                    conversion = midi_converter(mxl_path, midi_path)
                    if conversion.get("status") != "success":
                        raise RuntimeError(
                            str(conversion.get("message") or "MIDI conversion failed")
                        )
                    midi_result_path = midi_path if midi_path.is_file() else Path(
                        conversion.get("midi_path", midi_path)
                    )
                status = "recovered_midi"
            except Exception as exception:
                error = str(exception)
                if mxl_path is not None:
                    status = "recovered_mxl"
                else:
                    status = "still_failed"

        runtime = max(0.0, clock() - started)
        rows.append(
            {
                "doc_id": doc_id,
                "page_index": page_index,
                "primary_failure_status": page["primary_failure_status"],
                "fallback_400_status": status,
                "fallback_400_mxl_path": _relative(mxl_path),
                "fallback_400_midi_path": _relative(midi_result_path),
                "fallback_400_runtime_seconds": round(runtime, 6),
                "fallback_400_error": error,
                "run_action": action,
            }
        )
    return rows


def calculate_fallback_summary(
    rows: list[dict[str, object]],
    *,
    total_300dpi_failures: int,
    sample_total: int | None,
) -> dict[str, int | float | None]:
    attempted = len(rows)
    recovered_mxl = sum(
        row["fallback_400_status"] in {"recovered_mxl", "recovered_midi"}
        for row in rows
    )
    recovered_midi = sum(
        row["fallback_400_status"] == "recovered_midi" for row in rows
    )
    still_failed = attempted - recovered_mxl
    combined = None
    if sample_total:
        primary_success = sample_total - total_300dpi_failures
        combined = (primary_success + recovered_midi) / sample_total
    return {
        "total_300dpi_failures": total_300dpi_failures,
        "attempted_400dpi": attempted,
        "recovered_mxl": recovered_mxl,
        "recovered_midi": recovered_midi,
        "still_failed": still_failed,
        "fallback_recovery_rate": recovered_mxl / attempted if attempted else 0.0,
        "combined_success_rate": combined,
        "fallback_runtime_seconds": sum(
            float(row["fallback_400_runtime_seconds"]) for row in rows
        ),
    }


def build_summary_markdown(summary: dict[str, int | float | None]) -> str:
    combined = summary["combined_success_rate"]
    combined_text = f"{float(combined):.2%}" if combined is not None else "н/д"
    return f"""# OMR fallback experiment: 400 DPI

Эксперимент включает только страницы, для которых основной OMR при 300 DPI не
создал MXL. Результаты fallback не заменяют и не смешиваются с основной
метрикой: они показываются отдельным дополнительным этапом восстановления.

| Показатель | Значение |
|---|---:|
| Failures основного OMR 300 DPI | {summary['total_300dpi_failures']} |
| Попыток fallback 400 DPI | {summary['attempted_400dpi']} |
| Восстановлено MXL | {summary['recovered_mxl']} |
| Восстановлено MIDI | {summary['recovered_midi']} |
| Остались без MXL | {summary['still_failed']} |
| Fallback recovery rate | {float(summary['fallback_recovery_rate']):.2%} |
| Combined technical success rate | {combined_text} |
| Runtime fallback, секунд | {float(summary['fallback_runtime_seconds']):.2f} |

`combined_success_rate` рассчитывается относительно исходной OMR-выборки как
`(primary_300dpi_MXL+MIDI_success + recovered_MIDI_400dpi) / sample_total`.
Страница только с восстановленным MXL, но без MIDI, не повышает этот показатель.
Это комбинированная техническая успешность pipeline, а не экспертная оценка
музыкальной точности MusicXML.
"""


def write_reports(
    rows: list[dict[str, object]],
    summary: dict[str, int | float | None],
    report_path: Path,
    summary_path: Path,
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(build_summary_markdown(summary), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--omr-report",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "reports" / "omr_pipeline_report.csv",
    )
    parser.add_argument("--failure-report", type=Path)
    parser.add_argument("--pages-dir", type=Path, default=PROJECT_ROOT / "outputs/pages")
    parser.add_argument("--raw-dir", type=Path, default=PROJECT_ROOT / "data/raw")
    parser.add_argument(
        "--out-dir", type=Path, default=PROJECT_ROOT / "outputs/omr_400dpi_fallback"
    )
    parser.add_argument(
        "--midi-dir", type=Path, default=PROJECT_ROOT / "outputs/midi_400dpi_fallback"
    )
    parser.add_argument("--dpi", type=int, default=400)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--doc-id")
    parser.add_argument("--page-index", type=int)
    parser.add_argument("--audiveris-bin", default="audiveris")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        pages, context = select_failed_pages(
            args.omr_report,
            failure_report=args.failure_report,
            doc_id=args.doc_id,
            page_index=args.page_index,
            limit=args.limit,
        )
        rows = run_fallback_pages(
            pages,
            raw_dir=args.raw_dir,
            pages_dir=args.pages_dir,
            out_dir=args.out_dir,
            midi_dir=args.midi_dir,
            dpi=args.dpi,
            skip_existing=args.skip_existing or args.resume,
            resume=args.resume,
            audiveris_bin=args.audiveris_bin,
        )
        summary = calculate_fallback_summary(
            rows,
            total_300dpi_failures=int(context["total_300dpi_failures"] or 0),
            sample_total=context["sample_total"],
        )
        write_reports(rows, summary, args.report_out, args.summary_out)
    except (FileNotFoundError, ValueError, OSError, csv.Error) as error:
        raise SystemExit(f"Error: {error}") from error

    print(f"300 DPI failures: {summary['total_300dpi_failures']}")
    print(f"Attempted at {args.dpi} DPI: {summary['attempted_400dpi']}")
    print(f"Recovered MXL: {summary['recovered_mxl']}")
    print(f"Recovered MIDI: {summary['recovered_midi']}")
    print(f"Still failed: {summary['still_failed']}")
    print(f"Report: {args.report_out}")
    print(f"Summary: {args.summary_out}")


if __name__ == "__main__":
    main()
