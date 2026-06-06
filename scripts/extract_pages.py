"""Extract PDF pages and save a CSV manifest."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from notevision.pdf.extract_pages import extract_pdf_pages, find_pdf_in_document_dir


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, help="Path to a specific PDF file")
    parser.add_argument(
        "--document-dir",
        type=Path,
        help="Directory containing exactly one PDF file",
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Directory for page images and manifest.csv",
    )
    parser.add_argument(
        "--doc-id",
        default=None,
        help="Document ID; defaults to the PDF parent directory name",
    )
    parser.add_argument("--dpi", default=200, type=int, help="Rendering DPI")
    args = parser.parse_args()
    if args.pdf is None and args.document_dir is None:
        parser.error("one of --pdf or --document-dir is required")
    return args


def main() -> None:
    """Run page extraction and write the manifest."""
    args = parse_args()
    if args.pdf is not None:
        pdf_path = args.pdf
        doc_id = args.doc_id
    else:
        pdf_path = find_pdf_in_document_dir(args.document_dir)
        doc_id = args.doc_id or args.document_dir.resolve().name

    manifest = extract_pdf_pages(pdf_path, args.out, doc_id, args.dpi)
    manifest_path = args.out / "manifest.csv"
    manifest.to_csv(manifest_path, index=False)

    print(f"Processed pages: {len(manifest)}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
