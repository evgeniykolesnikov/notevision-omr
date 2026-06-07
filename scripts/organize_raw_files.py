"""Organize downloaded RSL PDF and MRC files by document ID."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from notevision.metadata.file_matching import organize_raw_files

DEFAULT_REPORT_PATH = PROJECT_ROOT / "outputs" / "reports" / "raw_import_report.csv"


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inbox", required=True, type=Path)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument(
        "--move",
        action="store_true",
        help="Move source files instead of copying them",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace files that already exist in the destination",
    )
    return parser.parse_args()


def main() -> None:
    """Organize files and save the import report."""
    args = parse_args()
    rows = organize_raw_files(
        args.inbox,
        args.raw_dir,
        move=args.move,
        overwrite=args.overwrite,
        report_path=DEFAULT_REPORT_PATH,
    )

    successful = sum(row["status"] in {"copied", "moved"} for row in rows)
    warnings = sum(row["status"] == "warning" for row in rows)
    errors = sum(row["status"] == "error" for row in rows)
    skipped = sum(row["status"] == "skipped" for row in rows)
    print(f"Imported files: {successful}")
    print(f"Skipped files: {skipped}")
    print(f"Warnings: {warnings}")
    print(f"Errors: {errors}")
    print(f"Report: {DEFAULT_REPORT_PATH}")


if __name__ == "__main__":
    main()
