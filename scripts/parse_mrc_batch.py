"""Parse MRC metadata for every document directory."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from notevision.metadata.parse_mrc import (
    METADATA_FIELDS,
    find_mrc_in_document_dir,
    parse_mrc_file,
)

ERROR_COLUMNS = ["doc_id", "document_dir", "error_type", "error"]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value


def main() -> None:
    """Parse all document folders and save metadata and errors."""
    args = parse_args()
    if not args.raw_dir.is_dir():
        raise FileNotFoundError(f"Raw data directory does not exist: {args.raw_dir}")

    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    document_dirs = sorted(
        (path for path in args.raw_dir.iterdir() if path.is_dir()),
        key=lambda path: path.name.lower(),
    )

    for document_dir in document_dirs:
        doc_id = document_dir.name
        try:
            mrc_path = find_mrc_in_document_dir(document_dir)
            metadata = parse_mrc_file(mrc_path, doc_id)
            rows.append(
                {key: _csv_value(metadata.get(key)) for key in METADATA_FIELDS}
            )
        except Exception as error:
            errors.append(
                {
                    "doc_id": doc_id,
                    "document_dir": str(document_dir),
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=METADATA_FIELDS).to_csv(args.out, index=False)

    errors_path = args.out.parent / "mrc_parse_errors.csv"
    pd.DataFrame(errors, columns=ERROR_COLUMNS).to_csv(errors_path, index=False)

    print(f"Parsed documents: {len(rows)}")
    print(f"Errors: {len(errors)}")
    print(f"Metadata: {args.out}")
    print(f"Error report: {errors_path}")


if __name__ == "__main__":
    main()
