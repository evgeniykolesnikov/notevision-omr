"""Extract raster page images from PDF documents."""

from pathlib import Path
from typing import Union

import pandas as pd

PathLike = Union[str, Path]

MANIFEST_COLUMNS = [
    "doc_id",
    "page_index",
    "image_path",
    "width",
    "height",
    "dpi",
]


def find_pdf_in_document_dir(document_dir: PathLike) -> Path:
    """Return the only PDF located directly inside a document directory.

    Raises:
        FileNotFoundError: If the directory contains no PDF files.
        ValueError: If the directory contains more than one PDF file.
    """
    directory = Path(document_dir)
    if directory.is_dir():
        pdf_files = sorted(
            (
                path
                for path in directory.iterdir()
                if path.is_file() and path.suffix.lower() == ".pdf"
            ),
            key=lambda path: path.name.lower(),
        )
    else:
        pdf_files = []

    if not pdf_files:
        raise FileNotFoundError(f"No PDF file found in document directory: {directory}")
    if len(pdf_files) > 1:
        found_files = ", ".join(str(path) for path in pdf_files)
        raise ValueError(
            f"Multiple PDF files found in document directory {directory}: "
            f"{found_files}"
        )

    return pdf_files[0]


def extract_pdf_pages(
    pdf_path: PathLike,
    output_dir: PathLike,
    doc_id: str | None = None,
    dpi: int = 200,
) -> pd.DataFrame:
    """Render every PDF page as PNG and return its manifest.

    Args:
        pdf_path: Path to the source PDF.
        output_dir: Directory where page images will be written.
        doc_id: Document identifier. Defaults to the PDF parent directory name.
        dpi: Rendering resolution in dots per inch.

    Raises:
        FileNotFoundError: If ``pdf_path`` does not exist.
        ValueError: If ``pdf_path`` is not a file or ``dpi`` is not positive.
    """
    import pymupdf

    source = Path(pdf_path)
    destination = Path(output_dir)

    if not source.exists():
        raise FileNotFoundError(f"PDF file does not exist: {source}")
    if not source.is_file():
        raise ValueError(f"PDF path is not a file: {source}")
    if dpi <= 0:
        raise ValueError(f"DPI must be a positive integer, got: {dpi}")

    resolved_doc_id = (
        doc_id if doc_id is not None else source.resolve().parent.name
    )
    destination.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, object]] = []
    with pymupdf.open(str(source)) as document:
        for page_index, page in enumerate(document, start=1):
            image_path = destination / f"page_{page_index:03d}.png"
            pixmap = page.get_pixmap(dpi=dpi, alpha=False)
            pixmap.save(str(image_path))
            records.append(
                {
                    "doc_id": resolved_doc_id,
                    "page_index": page_index,
                    "image_path": str(image_path),
                    "width": pixmap.width,
                    "height": pixmap.height,
                    "dpi": dpi,
                }
            )

    return pd.DataFrame(records, columns=MANIFEST_COLUMNS)
