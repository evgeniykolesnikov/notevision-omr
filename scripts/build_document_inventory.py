"""Build a CSV inventory for the thesis document corpus."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from notevision.metadata.parse_mrc import parse_mrc_file
from notevision.pdf.extract_pages import find_pdf_in_document_dir

INVENTORY_COLUMNS = [
    "doc_id",
    "title",
    "authors",
    "year",
    "language",
    "publication",
    "physical_description",
    "record_id",
    "source_url",
    "pages_count",
    "pdf_status",
    "mrc_status",
    "processing_status",
    "scan_quality",
    "music_pages_count",
    "omr_status",
    "comments",
]


def find_document_dirs(raw_dir: Path) -> list[Path]:
    """Return document subdirectories in deterministic order."""
    if not raw_dir.is_dir():
        raise FileNotFoundError(f"Raw data directory does not exist: {raw_dir}")
    return sorted(
        (path for path in raw_dir.iterdir() if path.is_dir()),
        key=lambda path: path.name.lower(),
    )


def find_marc_in_document_dir(document_dir: Path) -> Path:
    """Return the only MRC or MARC file in a document directory."""
    metadata_files = sorted(
        (
            path
            for path in document_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".mrc", ".marc"}
        ),
        key=lambda path: path.name.lower(),
    )
    if not metadata_files:
        raise FileNotFoundError(
            f"No MRC/MARC file found in document directory: {document_dir}"
        )
    if len(metadata_files) > 1:
        found_files = ", ".join(str(path) for path in metadata_files)
        raise ValueError(
            f"Multiple MRC/MARC files found in document directory "
            f"{document_dir}: {found_files}"
        )
    return metadata_files[0]


def _join_values(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(str(item) for item in value if item)
    return str(value)


def _count_pdf_pages(pdf_path: Path) -> int:
    import pymupdf

    with pymupdf.open(str(pdf_path)) as document:
        return len(document)


def build_inventory_row(document_dir: Path) -> dict[str, Any]:
    """Build one inventory row without propagating document-level errors."""
    row: dict[str, Any] = {
        "doc_id": document_dir.name,
        "title": "",
        "authors": "",
        "year": "",
        "language": "",
        "publication": "",
        "physical_description": "",
        "record_id": "",
        "source_url": "",
        "pages_count": "",
        "pdf_status": "missing",
        "mrc_status": "missing",
        "processing_status": "imported",
        "scan_quality": "unknown",
        "music_pages_count": "",
        "omr_status": "not_started",
        "comments": "",
    }
    errors: list[str] = []

    try:
        pdf_path = find_pdf_in_document_dir(document_dir)
    except FileNotFoundError:
        pass
    except Exception as error:
        row["pdf_status"] = "error"
        errors.append(f"PDF: {error}")
    else:
        try:
            row["pages_count"] = _count_pdf_pages(pdf_path)
            row["pdf_status"] = "exists"
        except Exception as error:
            row["pdf_status"] = "error"
            errors.append(f"PDF: {error}")

    try:
        mrc_path = find_marc_in_document_dir(document_dir)
    except FileNotFoundError:
        pass
    except Exception as error:
        row["mrc_status"] = "error"
        errors.append(f"MRC: {error}")
    else:
        try:
            metadata = parse_mrc_file(mrc_path, doc_id=document_dir.name)
            row.update(
                {
                    "title": metadata.get("title") or "",
                    "authors": _join_values(metadata.get("authors")),
                    "year": metadata.get("year") or "",
                    "language": metadata.get("language") or "",
                    "publication": metadata.get("publication") or "",
                    "physical_description": (
                        metadata.get("physical_description") or ""
                    ),
                    "record_id": metadata.get("record_id") or "",
                    "source_url": _join_values(
                        metadata.get("electronic_resources")
                    ),
                    "mrc_status": "parsed",
                }
            )
        except Exception as error:
            row["mrc_status"] = "error"
            errors.append(f"MRC: {error}")

    row["comments"] = " | ".join(errors)
    return row


def build_document_inventory(raw_dir: Path) -> pd.DataFrame:
    """Build an inventory DataFrame for every document under ``raw_dir``."""
    rows = [
        build_inventory_row(document_dir)
        for document_dir in find_document_dirs(raw_dir)
    ]
    return pd.DataFrame(rows, columns=INVENTORY_COLUMNS)


def write_document_inventory(raw_dir: Path, output_path: Path) -> pd.DataFrame:
    """Build and save the thesis corpus inventory."""
    inventory = build_document_inventory(raw_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    inventory.to_csv(output_path, index=False)
    return inventory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    inventory = write_document_inventory(args.raw_dir, args.out)
    error_documents = (
        (inventory["pdf_status"] == "error")
        | (inventory["mrc_status"] == "error")
    )

    print(f"Documents found: {len(inventory)}")
    print(f"PDF exists: {int((inventory['pdf_status'] == 'exists').sum())}")
    print(f"MRC parsed: {int((inventory['mrc_status'] == 'parsed').sum())}")
    print(f"Errors: {int(error_documents.sum())}")
    print(f"Inventory: {args.out}")


if __name__ == "__main__":
    main()
