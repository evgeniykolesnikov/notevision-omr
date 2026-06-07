"""Match downloaded RSL files and organize them by document ID."""

from __future__ import annotations

import csv
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Union

PathLike = Union[str, Path]

REPORT_COLUMNS = [
    "original_path",
    "target_path",
    "doc_id",
    "file_type",
    "status",
    "message",
]


def normalize_doc_id(value: PathLike) -> str:
    """Normalize a supported RSL identifier to the ``rsl01...`` form.

    Eleven-digit identifiers are used directly. A nine-digit identifier is
    expanded by the known RSL convention of prefixing ``01``. Other lengths
    are rejected because guessing them could associate files incorrectly.
    """
    name = Path(str(value)).name
    stem = Path(name).stem.lower().strip()
    if stem.startswith("rsl"):
        stem = stem[3:]

    if not stem.isdigit():
        raise ValueError(f"Could not determine numeric RSL ID from: {value}")
    if len(stem) == 9:
        stem = f"01{stem}"
    elif len(stem) != 11:
        raise ValueError(
            "RSL ID must contain 11 digits, or 9 digits eligible for the "
            f"documented '01' prefix rule: {value}"
        )

    return f"rsl{stem}"


def detect_doc_id_from_filename(path: PathLike) -> str:
    """Determine an RSL document ID from a downloaded PDF or MRC filename."""
    source = Path(path)
    if source.suffix.lower() not in {".pdf", ".mrc"}:
        raise ValueError(f"Unsupported source file type: {source}")
    return normalize_doc_id(source.name)


def _write_source_file(
    source_path: Path,
    doc_id: str,
    imported_from: Path,
) -> None:
    if source_path.exists():
        return

    imported_at = datetime.now(timezone.utc).isoformat()
    source_path.write_text(
        "\n".join(
            [
                f"doc_id: {doc_id}",
                f"imported_from: {imported_from}",
                f"import_date: {imported_at}",
                "notes:",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_report(report_path: Path, rows: list[dict[str, str]]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8-sig", newline="") as report_file:
        writer = csv.DictWriter(report_file, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def organize_raw_files(
    inbox: PathLike,
    raw_dir: PathLike,
    *,
    move: bool = False,
    overwrite: bool = False,
    report_path: PathLike | None = None,
) -> list[dict[str, str]]:
    """Copy or move downloaded PDF/MRC files into document directories."""
    inbox_path = Path(inbox)
    raw_path = Path(raw_dir)
    if not inbox_path.is_dir():
        raise FileNotFoundError(f"Inbox directory does not exist: {inbox_path}")

    raw_path.mkdir(parents=True, exist_ok=True)
    source_files = sorted(
        (
            path
            for path in inbox_path.iterdir()
            if path.is_file() and path.suffix.lower() in {".pdf", ".mrc"}
        ),
        key=lambda path: path.name.lower(),
    )

    report_rows: list[dict[str, str]] = []
    touched_documents: dict[str, Path] = {}

    for source in source_files:
        file_type = source.suffix.lower().lstrip(".")
        try:
            doc_id = detect_doc_id_from_filename(source)
        except ValueError as error:
            report_rows.append(
                {
                    "original_path": str(source),
                    "target_path": "",
                    "doc_id": "",
                    "file_type": file_type,
                    "status": "error",
                    "message": str(error),
                }
            )
            continue

        document_dir = raw_path / doc_id
        document_dir.mkdir(parents=True, exist_ok=True)
        touched_documents[doc_id] = document_dir
        target = document_dir / source.name

        if target.exists() and not overwrite:
            status = "skipped"
            message = "Target already exists; use --overwrite to replace it"
        else:
            if target.exists():
                target.unlink()
            if move:
                shutil.move(str(source), str(target))
                status = "moved"
            else:
                shutil.copy2(source, target)
                status = "copied"
            message = ""

        _write_source_file(
            document_dir / "source.txt",
            doc_id,
            inbox_path.resolve(),
        )
        report_rows.append(
            {
                "original_path": str(source),
                "target_path": str(target),
                "doc_id": doc_id,
                "file_type": file_type,
                "status": status,
                "message": message,
            }
        )

    for doc_id, document_dir in sorted(touched_documents.items()):
        present_types = {
            path.suffix.lower()
            for path in document_dir.iterdir()
            if path.is_file()
        }
        for suffix, label in ((".pdf", "PDF"), (".mrc", "MRC")):
            if suffix not in present_types:
                report_rows.append(
                    {
                        "original_path": str(inbox_path),
                        "target_path": str(document_dir),
                        "doc_id": doc_id,
                        "file_type": suffix.lstrip("."),
                        "status": "warning",
                        "message": f"{label} file is missing for document",
                    }
                )

    if report_path is not None:
        _write_report(Path(report_path), report_rows)

    return report_rows
