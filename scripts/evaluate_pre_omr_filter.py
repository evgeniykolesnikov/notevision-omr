"""Evaluate an experimental pre-OMR filter on candidate page PNG files."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from notevision.omr.pre_omr_filter import (  # noqa: E402
    evaluate_against_labels,
    format_markdown_report,
    load_csv_rows,
    run_pre_omr_filter,
    write_predictions_csv,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--pages-dir", required=True, type=Path)
    parser.add_argument(
        "--failure-review",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "reports" / "failure_review.csv",
        help="CSV export from review_app failure review.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "reports" / "pre_omr_filter_eval.md",
    )
    parser.add_argument(
        "--predictions-out",
        type=Path,
        default=PROJECT_ROOT
        / "outputs"
        / "reports"
        / "pre_omr_filter_predictions.csv",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        candidate_rows = load_csv_rows(args.candidates)
        failure_review_rows = (
            load_csv_rows(args.failure_review)
            if args.failure_review and args.failure_review.is_file()
            else []
        )
        predictions = run_pre_omr_filter(
            candidate_rows,
            pages_dir=args.pages_dir,
            project_root=PROJECT_ROOT,
        )
        write_predictions_csv(args.predictions_out, predictions)
        metrics = evaluate_against_labels(
            predictions,
            candidate_rows,
            failure_review_rows,
        )
        report = format_markdown_report(
            metrics,
            candidates_path=args.candidates,
            failure_review_path=(
                args.failure_review if args.failure_review.is_file() else None
            ),
            predictions_path=args.predictions_out,
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
    except (FileNotFoundError, ValueError, OSError, csv.Error) as error:
        raise SystemExit(f"Error: {error}") from error

    print(f"Candidates: {metrics['total_candidates']}")
    print(f"Filtered out: {metrics['filtered_out']}")
    print(
        "false_positive_music filtered: "
        f"{metrics['false_positive_music_filtered']}/"
        f"{metrics['false_positive_music_total']}"
    )
    print(
        "music/mixed wrongly filtered: "
        f"{metrics['music_mixed_wrongly_filtered']}/"
        f"{metrics['music_mixed_total']}"
    )
    print(f"Report: {args.out}")
    print(f"Predictions: {args.predictions_out}")


if __name__ == "__main__":
    main()
