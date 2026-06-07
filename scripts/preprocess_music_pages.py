"""Preprocess labeled music pages for OMR."""

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from notevision.preprocessing.music_pages import preprocess_music_pages

REPORT_PATH = PROJECT_ROOT / "outputs" / "reports" / "preprocessing_report.csv"


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    """Preprocess music pages and save the batch report."""
    args = parse_args()
    if not args.labels.is_file():
        raise FileNotFoundError(f"Labels file does not exist: {args.labels}")

    labels = pd.read_csv(args.labels)
    report = preprocess_music_pages(
        labels,
        args.out_dir,
        project_root=PROJECT_ROOT,
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(REPORT_PATH, index=False)

    successful = int((report["status"] == "success").sum())
    errors = int((report["status"] == "error").sum())
    print(f"Music pages selected: {len(report)}")
    print(f"Preprocessed pages: {successful}")
    print(f"Errors: {errors}")
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
