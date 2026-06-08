"""Profile Audiveris runtime from an OMR report and native log files."""

from __future__ import annotations

import argparse
import csv
import re
import statistics
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = PROJECT_ROOT / "outputs" / "reports" / "omr_report.csv"
DEFAULT_LABELS = PROJECT_ROOT / "data" / "labels" / "pages_validated_thesis.csv"
DEFAULT_PAGES_OUT = (
    PROJECT_ROOT / "outputs" / "reports" / "omr_runtime_pages.csv"
)
DEFAULT_SUMMARY_OUT = (
    PROJECT_ROOT / "outputs" / "reports" / "omr_runtime_summary.csv"
)
DEFAULT_ESTIMATES_OUT = (
    PROJECT_ROOT / "outputs" / "reports" / "omr_runtime_estimates.csv"
)

REPORT_REQUIRED_COLUMNS = {
    "doc_id",
    "page_index",
    "output_dir",
    "status",
}
LABEL_REQUIRED_COLUMNS = {
    "doc_id",
    "page_type",
    "has_music",
}
PAGE_OUTPUT_COLUMNS = [
    "doc_id",
    "page_index",
    "status",
    "output_dir",
    "log_path",
    "started_at",
    "finished_at",
    "duration_seconds",
    "measurement_status",
    "measurement_message",
]
SUMMARY_OUTPUT_COLUMNS = [
    "status",
    "pages",
    "mean_seconds",
    "median_seconds",
    "p90_seconds",
    "p95_seconds",
    "fastest_doc_id",
    "fastest_page_index",
    "fastest_seconds",
    "slowest_doc_id",
    "slowest_page_index",
    "slowest_seconds",
]
ESTIMATE_OUTPUT_COLUMNS = [
    "documents",
    "workers",
    "pages_per_document",
    "estimated_pages",
    "mean_seconds_per_page",
    "estimated_seconds",
    "estimated_hours",
    "estimated_days",
    "estimated_years",
    "parallelism_assumption",
]
DOCUMENT_SCALES = (100, 1000, 10000, 87963)
WORKER_COUNTS = (1, 2, 4, 8)
TIMESTAMP_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})"
)
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S,%f"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Read a CSV file and return its rows as dictionaries."""
    if not path.is_file():
        raise FileNotFoundError(f"CSV file does not exist: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def validate_columns(
    rows: Sequence[dict[str, str]],
    required: set[str],
    source_name: str,
) -> None:
    """Validate required columns even when a CSV has no data rows."""
    if not rows:
        raise ValueError(f"{source_name} contains no rows.")
    missing = required.difference(rows[0])
    if missing:
        names = ", ".join(sorted(missing))
        raise ValueError(f"{source_name} is missing required columns: {names}")


def find_latest_native_log(output_dir: Path) -> Path | None:
    """Find the latest Audiveris-native log, excluding wrapper logs."""
    if not output_dir.is_dir():
        return None
    logs = [
        path
        for path in output_dir.glob("*.log")
        if not path.name.endswith("_audiveris.log")
    ]
    if not logs:
        return None
    return max(logs, key=lambda path: path.stat().st_mtime_ns)


def parse_native_log_runtime(
    log_path: Path,
) -> tuple[datetime, datetime, float]:
    """Return the first timestamp, last timestamp, and elapsed seconds."""
    timestamps: list[datetime] = []
    with log_path.open("r", encoding="utf-8", errors="replace") as log_file:
        for line in log_file:
            match = TIMESTAMP_PATTERN.match(line)
            if match:
                timestamps.append(
                    datetime.strptime(match.group(1), TIMESTAMP_FORMAT)
                )
    if len(timestamps) < 2:
        raise ValueError(
            f"Native Audiveris log has fewer than two timestamps: {log_path}"
        )
    started_at = timestamps[0]
    finished_at = timestamps[-1]
    duration = (finished_at - started_at).total_seconds()
    if duration < 0:
        raise ValueError(f"Log timestamps are out of order: {log_path}")
    return started_at, finished_at, duration


def collect_runtime_measurements(
    report_rows: Sequence[dict[str, str]],
    *,
    base_dir: Path = PROJECT_ROOT,
) -> list[dict[str, object]]:
    """Collect page runtimes by matching report rows to native logs."""
    validate_columns(report_rows, REPORT_REQUIRED_COLUMNS, "OMR report")
    measurements: list[dict[str, object]] = []

    for row in report_rows:
        output_dir = Path(row["output_dir"])
        if not output_dir.is_absolute():
            output_dir = base_dir / output_dir
        log_path = find_latest_native_log(output_dir)
        measurement: dict[str, object] = {
            "doc_id": row["doc_id"],
            "page_index": int(row["page_index"]),
            "status": row["status"].strip().lower(),
            "output_dir": str(output_dir),
            "log_path": str(log_path) if log_path else "",
            "started_at": "",
            "finished_at": "",
            "duration_seconds": "",
            "measurement_status": "missing_log",
            "measurement_message": (
                f"No native Audiveris log found in: {output_dir}"
            ),
        }
        if log_path is not None:
            try:
                started_at, finished_at, duration = parse_native_log_runtime(
                    log_path
                )
            except (OSError, ValueError) as error:
                measurement["measurement_status"] = "invalid_log"
                measurement["measurement_message"] = str(error)
            else:
                measurement.update(
                    {
                        "started_at": started_at.isoformat(timespec="milliseconds"),
                        "finished_at": finished_at.isoformat(
                            timespec="milliseconds"
                        ),
                        "duration_seconds": round(duration, 3),
                        "measurement_status": "measured",
                        "measurement_message": "",
                    }
                )
        measurements.append(measurement)

    return measurements


def percentile(values: Sequence[float], probability: float) -> float:
    """Calculate a linearly interpolated percentile."""
    if not values:
        raise ValueError("Cannot calculate a percentile of an empty sequence.")
    if not 0 <= probability <= 1:
        raise ValueError("probability must be between 0 and 1.")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - lower_index
    return ordered[lower_index] + (
        ordered[upper_index] - ordered[lower_index]
    ) * fraction


def summarize_runtimes(
    measurements: Sequence[dict[str, object]],
    statuses: Iterable[str] = ("success", "failed"),
) -> list[dict[str, object]]:
    """Summarize measured runtimes separately for each requested status."""
    summaries: list[dict[str, object]] = []
    measured = [
        row
        for row in measurements
        if row["measurement_status"] == "measured"
    ]

    for status in statuses:
        rows = [row for row in measured if row["status"] == status]
        if not rows:
            summaries.append(
                {
                    column: status if column == "status" else ""
                    for column in SUMMARY_OUTPUT_COLUMNS
                }
            )
            summaries[-1]["pages"] = 0
            continue

        durations = [float(row["duration_seconds"]) for row in rows]
        fastest = min(rows, key=lambda row: float(row["duration_seconds"]))
        slowest = max(rows, key=lambda row: float(row["duration_seconds"]))
        summaries.append(
            {
                "status": status,
                "pages": len(rows),
                "mean_seconds": round(statistics.fmean(durations), 3),
                "median_seconds": round(statistics.median(durations), 3),
                "p90_seconds": round(percentile(durations, 0.90), 3),
                "p95_seconds": round(percentile(durations, 0.95), 3),
                "fastest_doc_id": fastest["doc_id"],
                "fastest_page_index": fastest["page_index"],
                "fastest_seconds": fastest["duration_seconds"],
                "slowest_doc_id": slowest["doc_id"],
                "slowest_page_index": slowest["page_index"],
                "slowest_seconds": slowest["duration_seconds"],
            }
        )
    return summaries


def is_true(value: object) -> bool:
    """Interpret common CSV boolean and integer representations."""
    return str(value).strip().lower() in {"1", "1.0", "true", "yes"}


def calculate_pages_per_document(
    label_rows: Sequence[dict[str, str]],
) -> float:
    """Calculate eligible OMR pages per document from validated labels."""
    validate_columns(label_rows, LABEL_REQUIRED_COLUMNS, "Labels")
    document_ids = {
        row["doc_id"].strip() for row in label_rows if row["doc_id"].strip()
    }
    if not document_ids:
        raise ValueError("Labels contain no document identifiers.")
    eligible_pages = sum(
        is_true(row["has_music"])
        and row["page_type"].strip().lower() in {"music", "mixed"}
        for row in label_rows
    )
    return eligible_pages / len(document_ids)


def calculate_overall_mean(
    measurements: Sequence[dict[str, object]],
) -> float:
    """Calculate the observed mean across all measured pages."""
    durations = [
        float(row["duration_seconds"])
        for row in measurements
        if row["measurement_status"] == "measured"
    ]
    if not durations:
        raise ValueError("No measured page runtimes are available.")
    return statistics.fmean(durations)


def build_scale_estimates(
    *,
    mean_seconds_per_page: float,
    pages_per_document: float,
    document_scales: Sequence[int] = DOCUMENT_SCALES,
    worker_counts: Sequence[int] = WORKER_COUNTS,
) -> list[dict[str, object]]:
    """Estimate ideal elapsed time for document and worker scenarios."""
    if mean_seconds_per_page <= 0:
        raise ValueError("mean_seconds_per_page must be positive.")
    if pages_per_document < 0:
        raise ValueError("pages_per_document cannot be negative.")

    estimates: list[dict[str, object]] = []
    for documents in document_scales:
        if documents <= 0:
            raise ValueError("Document counts must be positive.")
        estimated_pages = documents * pages_per_document
        serial_seconds = estimated_pages * mean_seconds_per_page
        for workers in worker_counts:
            if workers <= 0:
                raise ValueError("Worker counts must be positive.")
            elapsed_seconds = serial_seconds / workers
            estimates.append(
                {
                    "documents": documents,
                    "workers": workers,
                    "pages_per_document": round(pages_per_document, 3),
                    "estimated_pages": round(estimated_pages),
                    "mean_seconds_per_page": round(
                        mean_seconds_per_page,
                        3,
                    ),
                    "estimated_seconds": round(elapsed_seconds, 3),
                    "estimated_hours": round(elapsed_seconds / 3600, 3),
                    "estimated_days": round(elapsed_seconds / 86400, 3),
                    "estimated_years": round(
                        elapsed_seconds / (86400 * 365.25),
                        3,
                    ),
                    "parallelism_assumption": "ideal_linear_no_overhead",
                }
            )
    return estimates


def write_csv(
    path: Path,
    rows: Sequence[dict[str, object]],
    columns: Sequence[str],
) -> None:
    """Write rows to a UTF-8 CSV file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--omr-report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument(
        "--pages-per-document",
        type=float,
        help=(
            "Override OMR-eligible pages per document instead of calculating "
            "it from --labels."
        ),
    )
    parser.add_argument("--pages-out", type=Path, default=DEFAULT_PAGES_OUT)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY_OUT)
    parser.add_argument(
        "--estimates-out",
        type=Path,
        default=DEFAULT_ESTIMATES_OUT,
    )
    return parser.parse_args()


def main() -> None:
    """Build page measurements, runtime statistics, and scale estimates."""
    args = parse_args()
    report_rows = read_csv_rows(args.omr_report)
    measurements = collect_runtime_measurements(report_rows)
    summaries = summarize_runtimes(measurements)

    if args.pages_per_document is None:
        label_rows = read_csv_rows(args.labels)
        pages_per_document = calculate_pages_per_document(label_rows)
    else:
        pages_per_document = args.pages_per_document

    mean_seconds = calculate_overall_mean(measurements)
    estimates = build_scale_estimates(
        mean_seconds_per_page=mean_seconds,
        pages_per_document=pages_per_document,
    )

    write_csv(args.pages_out, measurements, PAGE_OUTPUT_COLUMNS)
    write_csv(args.summary_out, summaries, SUMMARY_OUTPUT_COLUMNS)
    write_csv(args.estimates_out, estimates, ESTIMATE_OUTPUT_COLUMNS)

    measured_count = sum(
        row["measurement_status"] == "measured" for row in measurements
    )
    print(f"Report pages: {len(report_rows)}")
    print(f"Measured pages: {measured_count}")
    for summary in summaries:
        print(
            f"{str(summary['status']).capitalize()}: "
            f"{summary['pages']} pages, "
            f"mean {summary['mean_seconds']} s, "
            f"median {summary['median_seconds']} s, "
            f"p95 {summary['p95_seconds']} s"
        )
    print(f"OMR pages per document: {pages_per_document:.3f}")
    print(f"Page measurements: {args.pages_out}")
    print(f"Runtime summary: {args.summary_out}")
    print(f"Scale estimates: {args.estimates_out}")


if __name__ == "__main__":
    main()
