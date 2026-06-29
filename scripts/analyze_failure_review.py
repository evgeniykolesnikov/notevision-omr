"""Summarize manual OMR failure review export."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

DEFAULT_INPUT = Path("outputs/reports/omr_eval_300_failure_review_export_final.csv")
DEFAULT_SUMMARY_MD = Path("outputs/reports/omr_eval_300_failure_review_summary.md")
DEFAULT_SUMMARY_CSV = Path("outputs/reports/omr_eval_300_failure_review_summary.csv")

DISTRIBUTION_COLUMNS = (
    "corrected_page_type",
    "decision",
    "failure_reason",
    "classifier_error_type",
)
REAL_OMR_PAGE_TYPES = {"music", "mixed"}
HARD_NEGATIVE_PAGE_TYPES = {"cover", "title", "text", "blank"}


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        raise FileNotFoundError(f"Failure review CSV does not exist: {path}")
    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        return list(reader.fieldnames or []), list(reader)


def _value(row: dict[str, str], column: str) -> str:
    return str(row.get(column, "") or "").strip()


def _percent(count: int, total: int) -> float:
    return round((count / total * 100), 2) if total else 0.0


def _distribution(
    rows: list[dict[str, str]],
    fields: set[str],
    column: str,
) -> Counter[str]:
    if column not in fields:
        return Counter()
    return Counter(
        value
        for row in rows
        if (value := _value(row, column))
    )


def analyze_failure_review(
    rows: list[dict[str, str]],
    fields: list[str],
) -> dict[str, object]:
    """Compute distributions and derived failure-review metrics."""
    field_set = set(fields)
    total = len(rows)
    status_column = (
        "review_status"
        if "review_status" in field_set
        else "status"
        if "status" in field_set
        else ""
    )
    reviewed_rows = 0
    if status_column:
        reviewed_rows = sum(
            _value(row, status_column).lower() in {"reviewed", "completed"}
            for row in rows
        )

    distributions = {
        column: _distribution(rows, field_set, column)
        for column in DISTRIBUTION_COLUMNS
    }
    real_omr_cases = sum(
        _value(row, "corrected_page_type").lower() in REAL_OMR_PAGE_TYPES
        for row in rows
    )
    routing_errors = sum(
        _value(row, "classifier_error_type") == "false_positive_music"
        or _value(row, "decision") == "exclude_from_omr"
        for row in rows
    )
    hard_negatives = sum(
        _value(row, "corrected_page_type").lower() in HARD_NEGATIVE_PAGE_TYPES
        or _value(row, "classifier_error_type") == "false_positive_music"
        for row in rows
    )

    derived_counts = {
        "real_omr_cases": real_omr_cases,
        "routing_errors": routing_errors,
        "hard_negatives": hard_negatives,
    }
    return {
        "total_rows": total,
        "reviewed_rows": reviewed_rows,
        "status_column": status_column,
        "distributions": distributions,
        "derived_counts": derived_counts,
        "derived_percents": {
            name: _percent(count, total)
            for name, count in derived_counts.items()
        },
    }


def summary_csv_rows(metrics: dict[str, object]) -> list[dict[str, object]]:
    total = int(metrics["total_rows"])
    output_rows: list[dict[str, object]] = [
        {
            "section": "overview",
            "name": "total_rows",
            "count": total,
            "percent": _percent(total, total),
        },
        {
            "section": "overview",
            "name": "reviewed_rows",
            "count": int(metrics["reviewed_rows"]),
            "percent": _percent(int(metrics["reviewed_rows"]), total),
        },
    ]
    distributions = metrics["distributions"]
    assert isinstance(distributions, dict)
    for section, counter in distributions.items():
        assert isinstance(counter, Counter)
        for name, count in counter.most_common():
            output_rows.append(
                {
                    "section": section,
                    "name": name,
                    "count": count,
                    "percent": _percent(count, total),
                }
            )
    derived_counts = metrics["derived_counts"]
    assert isinstance(derived_counts, dict)
    for name, count in derived_counts.items():
        output_rows.append(
            {
                "section": "derived",
                "name": name,
                "count": count,
                "percent": _percent(int(count), total),
            }
        )
    return output_rows


def _format_distribution_section(
    title: str,
    counter: Counter[str],
    total: int,
) -> list[str]:
    lines = [f"## {title}", ""]
    if not counter:
        lines.append("No data: column is missing or empty.")
    else:
        lines.extend(
            f"- {name}: {count} ({_percent(count, total):.2f}%)"
            for name, count in counter.most_common()
        )
    lines.append("")
    return lines


def render_markdown_summary(
    metrics: dict[str, object],
    *,
    input_path: Path,
    summary_csv_path: Path,
) -> str:
    total = int(metrics["total_rows"])
    reviewed = int(metrics["reviewed_rows"])
    status_column = str(metrics["status_column"] or "not available")
    distributions = metrics["distributions"]
    derived_counts = metrics["derived_counts"]
    derived_percents = metrics["derived_percents"]
    assert isinstance(distributions, dict)
    assert isinstance(derived_counts, dict)
    assert isinstance(derived_percents, dict)

    lines = [
        "# Failure Review Summary",
        "",
        "## Inputs",
        "",
        f"- Input CSV: `{input_path.as_posix()}`",
        f"- Summary CSV: `{summary_csv_path.as_posix()}`",
        "",
        "## Overview",
        "",
        f"- Total rows: {total}",
        f"- Reviewed rows: {reviewed}",
        f"- Status column: `{status_column}`",
        "",
    ]
    lines.extend(
        _format_distribution_section(
            "Corrected Page Types",
            distributions["corrected_page_type"],
            total,
        )
    )
    lines.extend(
        _format_distribution_section(
            "Decisions",
            distributions["decision"],
            total,
        )
    )
    lines.extend(
        _format_distribution_section(
            "Failure Reasons",
            distributions["failure_reason"],
            total,
        )
    )
    lines.extend(
        _format_distribution_section(
            "Classifier Error Types",
            distributions["classifier_error_type"],
            total,
        )
    )
    lines.extend(
        [
            "## Derived Metrics",
            "",
            "- real_omr_cases: "
            f"{derived_counts['real_omr_cases']} "
            f"({derived_percents['real_omr_cases']:.2f}%)",
            "- routing_errors: "
            f"{derived_counts['routing_errors']} "
            f"({derived_percents['routing_errors']:.2f}%)",
            "- hard_negatives: "
            f"{derived_counts['hard_negatives']} "
            f"({derived_percents['hard_negatives']:.2f}%)",
            "",
            "## Interpretation",
            "",
            "Not all final failures are real OMR failures. Some cases are "
            "routing errors where non-music pages were sent to OMR.",
            "",
            "Routing errors and corrected non-music pages can be used as hard "
            "negative examples for further improvement of the page classifier.",
            "",
            "Real OMR cases, especially corrected `music` and `mixed` pages, "
            "require preprocessing/OMR improvements or additional manual review.",
            "",
        ]
    )
    return "\n".join(lines)


def write_summary_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=("section", "name", "count", "percent"),
        )
        writer.writeheader()
        writer.writerows(rows)


def analyze_file(
    input_path: Path,
    summary_md_path: Path,
    summary_csv_path: Path,
) -> dict[str, object]:
    fields, rows = read_csv_rows(input_path)
    metrics = analyze_failure_review(rows, fields)
    write_summary_csv(summary_csv_path, summary_csv_rows(metrics))
    summary_md_path.parent.mkdir(parents=True, exist_ok=True)
    summary_md_path.write_text(
        render_markdown_summary(
            metrics,
            input_path=input_path,
            summary_csv_path=summary_csv_path,
        ),
        encoding="utf-8",
    )
    return metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--summary-md", type=Path, default=DEFAULT_SUMMARY_MD)
    parser.add_argument("--summary-csv", type=Path, default=DEFAULT_SUMMARY_CSV)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        metrics = analyze_file(args.input, args.summary_md, args.summary_csv)
    except (FileNotFoundError, OSError, csv.Error, ValueError) as error:
        raise SystemExit(f"Error: {error}") from error
    print(f"Total rows: {metrics['total_rows']}")
    print(f"Reviewed rows: {metrics['reviewed_rows']}")
    derived = metrics["derived_counts"]
    assert isinstance(derived, dict)
    print(f"Real OMR cases: {derived['real_omr_cases']}")
    print(f"Routing errors: {derived['routing_errors']}")
    print(f"Hard negatives: {derived['hard_negatives']}")
    print(f"Markdown summary: {args.summary_md}")
    print(f"CSV summary: {args.summary_csv}")


if __name__ == "__main__":
    main()
