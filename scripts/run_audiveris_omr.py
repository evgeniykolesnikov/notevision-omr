"""Run experimental OMR through the Audiveris command-line interface."""

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from notevision.omr.audiveris import (
    REPORT_COLUMNS,
    find_existing_mxl,
    run_audiveris,
    run_audiveris_batch,
    run_audiveris_candidates,
    summarize_run_actions,
)

REPORT_PATH = PROJECT_ROOT / "outputs" / "reports" / "omr_report.csv"


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--input",
        type=Path,
        help="One preprocessed page image",
    )
    source_group.add_argument(
        "--labels",
        type=Path,
        help="Labels CSV for batch mode",
    )
    source_group.add_argument(
        "--candidates",
        type=Path,
        help="OMR candidates CSV for batch mode",
    )
    parser.add_argument(
        "--preprocessed-dir",
        type=Path,
        help="Root directory containing preprocessed pages",
    )
    parser.add_argument(
        "--omr-pages-dir",
        type=Path,
        help="Root directory containing high-resolution OMR pages",
    )
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--audiveris-bin", default="audiveris")
    parser.add_argument("--limit", type=int, help="Batch page limit")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Do not run Audiveris when an MXL already exists.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Resume an interrupted run: skip existing MXL files and process "
            "only unfinished pages."
        ),
    )
    args = parser.parse_args()

    if args.labels is not None and args.preprocessed_dir is None:
        parser.error("--preprocessed-dir is required with --labels")
    return args


def _single_report_row(
    input_path: Path,
    output_dir: Path,
    result: dict[str, object],
) -> pd.DataFrame:
    match = re.search(r"page_(\d+)", input_path.stem)
    page_index = int(match.group(1)) if match else 0
    return pd.DataFrame(
        [
            {
                "doc_id": input_path.parent.name,
                "page_index": page_index,
                "input_path": str(input_path),
                "input_kind": "preprocessed",
                "output_dir": str(output_dir),
                "status": result["status"],
                "message": result["message"],
                "run_action": result["run_action"],
            }
        ],
        columns=REPORT_COLUMNS,
    )


def main() -> None:
    """Run single-page or batch Audiveris processing."""
    args = parse_args()
    if args.input is not None:
        existing_mxl = None
        if args.skip_existing or args.resume:
            existing_mxl = find_existing_mxl(
                args.out_dir,
                input_path=args.input,
            )
        if existing_mxl is not None:
            result = {
                "status": "success",
                "message": f"Existing MXL found: {existing_mxl}",
                "run_action": "skipped",
            }
        else:
            result = run_audiveris(
                args.input,
                args.out_dir,
                audiveris_bin=args.audiveris_bin,
            )
            result["run_action"] = (
                "resumed" if args.resume else "processed"
            )
        report = _single_report_row(args.input, args.out_dir, result)
    elif args.labels is not None:
        if not args.labels.is_file():
            raise FileNotFoundError(f"Labels file does not exist: {args.labels}")
        labels = pd.read_csv(args.labels)
        report = run_audiveris_batch(
            labels,
            args.preprocessed_dir,
            args.out_dir,
            limit=args.limit,
            skip_existing=args.skip_existing,
            resume=args.resume,
            audiveris_bin=args.audiveris_bin,
        )
    else:
        if not args.candidates.is_file():
            raise FileNotFoundError(
                f"Candidates file does not exist: {args.candidates}"
            )
        candidates = pd.read_csv(args.candidates)
        report = run_audiveris_candidates(
            candidates,
            args.out_dir,
            omr_pages_dir=args.omr_pages_dir,
            limit=args.limit,
            skip_existing=args.skip_existing,
            resume=args.resume,
            audiveris_bin=args.audiveris_bin,
        )

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(REPORT_PATH, index=False)
    successful = int((report["status"] == "success").sum())
    failed = int((report["status"] == "failed").sum())
    action_counts = summarize_run_actions(report)
    print(f"Pages handled: {len(report)}")
    print(f"Skipped: {action_counts['skipped']}")
    print(f"Resumed: {action_counts['resumed']}")
    print(f"Processed: {action_counts['processed']}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
