"""Parse one MRC file and print its metadata as JSON."""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from notevision.metadata.parse_mrc import find_mrc_in_document_dir, parse_mrc_file


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mrc", type=Path, help="Path to a specific MRC file")
    parser.add_argument(
        "--document-dir",
        type=Path,
        help="Directory containing exactly one MRC file",
    )
    parser.add_argument("--doc-id", help="Document ID")
    parser.add_argument("--out", type=Path, help="Optional output JSON path")
    args = parser.parse_args()
    if args.mrc is None and args.document_dir is None:
        parser.error("one of --mrc or --document-dir is required")
    return args


def main() -> None:
    """Parse an MRC record, print JSON, and optionally save it."""
    args = parse_args()
    if args.mrc is not None:
        mrc_path = args.mrc
        doc_id = args.doc_id
    else:
        mrc_path = find_mrc_in_document_dir(args.document_dir)
        doc_id = args.doc_id or args.document_dir.resolve().name

    metadata = parse_mrc_file(mrc_path, doc_id)
    output = json.dumps(metadata, ensure_ascii=False, indent=2)
    print(output)

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(f"{output}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
