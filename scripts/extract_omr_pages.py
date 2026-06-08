"""Extract selected OMR candidate pages from source PDFs at high resolution."""

import argparse
import sys
from pathlib import Path
from typing import Any, Callable

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from notevision.pdf.extract_pages import find_pdf_in_document_dir
from notevision.omr.candidate_adapter import (
    NORMALIZED_SELECTED,
    adapt_omr_candidates,
)

REPORT_PATH = PROJECT_ROOT / "outputs" / "reports" / "omr_pages_report.csv"

REPORT_COLUMNS = [
    "doc_id",
    "page_index",
    "input_pdf",
    "output_path",
    "dpi",
    "status",
    "message",
]

def _default_pdf_opener(pdf_path: Path) -> Any:
    import pymupdf

    return pymupdf.open(str(pdf_path))


def extract_omr_candidate_pages(
    candidates: pd.DataFrame,
    raw_dir: Path,
    output_dir: Path,
    *,
    dpi: int = 300,
    limit: int | None = None,
    pdf_opener: Callable[[Path], Any] = _default_pdf_opener,
) -> pd.DataFrame:
    """Extract only candidate page indexes from each source PDF."""
    normalized = adapt_omr_candidates(candidates)
    if dpi <= 0:
        raise ValueError(f"DPI must be a positive integer, got: {dpi}")
    if limit is not None and limit <= 0:
        raise ValueError(f"limit must be a positive integer, got: {limit}")

    selected = normalized[normalized[NORMALIZED_SELECTED]].sort_values(
        ["doc_id", "page_index"],
        kind="stable",
    )
    if limit is not None:
        selected = selected.head(limit)

    report_rows: list[dict[str, object]] = []
    for doc_id, document_candidates in selected.groupby("doc_id", sort=False):
        document_dir = raw_dir / str(doc_id)
        try:
            pdf_path = find_pdf_in_document_dir(document_dir)
        except Exception as error:
            for page in document_candidates.itertuples(index=False):
                output_path = (
                    output_dir
                    / str(doc_id)
                    / f"page_{int(page.page_index):03d}.png"
                )
                report_rows.append(
                    {
                        "doc_id": doc_id,
                        "page_index": page.page_index,
                        "input_pdf": "",
                        "output_path": str(output_path),
                        "dpi": dpi,
                        "status": "error",
                        "message": str(error),
                    }
                )
            continue

        try:
            document = pdf_opener(pdf_path)
        except Exception as error:
            for page in document_candidates.itertuples(index=False):
                output_path = (
                    output_dir
                    / str(doc_id)
                    / f"page_{int(page.page_index):03d}.png"
                )
                report_rows.append(
                    {
                        "doc_id": doc_id,
                        "page_index": page.page_index,
                        "input_pdf": str(pdf_path),
                        "output_path": str(output_path),
                        "dpi": dpi,
                        "status": "error",
                        "message": f"Could not open PDF: {error}",
                    }
                )
            continue

        try:
            with document:
                for page in document_candidates.itertuples(index=False):
                    page_index = int(page.page_index)
                    output_path = (
                        output_dir
                        / str(doc_id)
                        / f"page_{page_index:03d}.png"
                    )
                    try:
                        if page_index < 1 or page_index > len(document):
                            raise IndexError(
                                f"Page index {page_index} is outside PDF range "
                                f"1..{len(document)}"
                            )
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        pdf_page = document[page_index - 1]
                        pixmap = pdf_page.get_pixmap(dpi=dpi, alpha=False)
                        pixmap.save(str(output_path))
                        status = "success"
                        message = ""
                    except Exception as error:
                        status = "error"
                        message = str(error)

                    report_rows.append(
                        {
                            "doc_id": doc_id,
                            "page_index": page_index,
                            "input_pdf": str(pdf_path),
                            "output_path": str(output_path),
                            "dpi": dpi,
                            "status": status,
                            "message": message,
                        }
                    )
        except Exception as error:
            report_rows.append(
                {
                    "doc_id": doc_id,
                    "page_index": 0,
                    "input_pdf": str(pdf_path),
                    "output_path": "",
                    "dpi": dpi,
                    "status": "error",
                    "message": f"PDF processing failed: {error}",
                }
            )

    return pd.DataFrame(report_rows, columns=REPORT_COLUMNS)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--dpi", default=300, type=int)
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


def main() -> None:
    """Extract candidate pages and save the page-level report."""
    args = parse_args()
    if not args.candidates.is_file():
        raise FileNotFoundError(
            f"Candidates file does not exist: {args.candidates}"
        )
    if not args.raw_dir.is_dir():
        raise FileNotFoundError(
            f"Raw data directory does not exist: {args.raw_dir}"
        )

    candidates = pd.read_csv(args.candidates, keep_default_na=False)
    report = extract_omr_candidate_pages(
        candidates,
        args.raw_dir,
        args.out_dir,
        dpi=args.dpi,
        limit=args.limit,
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(REPORT_PATH, index=False)

    successful = int((report["status"] == "success").sum())
    errors = int((report["status"] == "error").sum())
    print(f"Candidate pages selected: {len(report)}")
    print(f"Extracted pages: {successful}")
    print(f"Errors: {errors}")
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
