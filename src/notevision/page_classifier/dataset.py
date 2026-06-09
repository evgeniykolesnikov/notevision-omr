"""Dataset construction and leakage-safe document-level splitting."""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from pathlib import Path

MANUAL_SOURCES = frozenset({"manual_previous", "manual_thesis"})
PAGE_TYPES = frozenset(
    {"music", "mixed", "title", "text", "blank", "unknown"}
)


@dataclass(frozen=True)
class PageRecord:
    doc_id: str
    page_index: int
    image_path: Path
    target: int | str
    page_type: str
    has_music: int
    validation_source: str
    rule_based_pred: int | None = None


def _resolve_image_path(
    value: str,
    *,
    labels_path: Path,
    pages_dir: Path,
    doc_id: str,
    page_index: int,
) -> Path:
    normalized = Path(value.replace("\\", "/")) if value.strip() else Path()
    candidates = []
    if value.strip():
        candidates.append(
            normalized if normalized.is_absolute() else labels_path.parent.parent.parent / normalized
        )
    candidates.append(pages_dir / doc_id / f"page_{page_index:03d}.png")
    return next((path.resolve() for path in candidates if path.is_file()), candidates[-1].resolve())


def build_page_records(
    labels_path: Path,
    pages_dir: Path,
    *,
    target: str = "has_music",
    manual_only: bool = True,
) -> list[PageRecord]:
    """Build records, excluding automatic template labels by default."""
    if target not in {"has_music", "page_type"}:
        raise ValueError("target must be 'has_music' or 'page_type'")
    if not labels_path.is_file():
        raise FileNotFoundError(f"Labels CSV does not exist: {labels_path}")
    with labels_path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        required = {
            "doc_id",
            "page_index",
            "page_type",
            "has_music",
            "validation_source",
        }
        missing = sorted(required - set(reader.fieldnames or []))
        if missing:
            raise ValueError("Labels CSV is missing columns: " + ", ".join(missing))
        rows = list(reader)

    records = []
    for row in rows:
        source = str(row.get("validation_source", "")).strip()
        if manual_only and source not in MANUAL_SOURCES:
            continue
        doc_id = str(row.get("doc_id", "")).strip()
        page_type = str(row.get("page_type", "")).strip().lower() or "unknown"
        try:
            page_index = int(row["page_index"])
            has_music = int(float(row["has_music"]))
        except (TypeError, ValueError):
            continue
        if not doc_id or page_index < 1 or has_music not in {0, 1}:
            continue
        if target == "page_type" and page_type not in PAGE_TYPES:
            page_type = "unknown"
        rule_value = str(row.get("has_music_pred", "")).strip()
        rule_pred = int(float(rule_value)) if rule_value in {"0", "1", "0.0", "1.0"} else None
        records.append(
            PageRecord(
                doc_id=doc_id,
                page_index=page_index,
                image_path=_resolve_image_path(
                    str(row.get("image_path", "")),
                    labels_path=labels_path,
                    pages_dir=pages_dir,
                    doc_id=doc_id,
                    page_index=page_index,
                ),
                target=has_music if target == "has_music" else page_type,
                page_type=page_type,
                has_music=has_music,
                validation_source=source,
                rule_based_pred=rule_pred,
            )
        )
    return records


def split_by_document(
    records: list[PageRecord],
    *,
    validation_fraction: float = 0.2,
    random_seed: int = 42,
) -> tuple[list[PageRecord], list[PageRecord]]:
    """Split by document so no document leaks across train and validation."""
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction must be between 0 and 1")
    documents = sorted({record.doc_id for record in records})
    if len(documents) < 2:
        raise ValueError("At least two documents are required for document split")
    random.Random(random_seed).shuffle(documents)
    validation_count = max(1, min(len(documents) - 1, round(len(documents) * validation_fraction)))
    validation_docs = set(documents[:validation_count])
    train = [record for record in records if record.doc_id not in validation_docs]
    validation = [record for record in records if record.doc_id in validation_docs]
    return train, validation


def existing_records(
    records: list[PageRecord],
) -> tuple[list[PageRecord], list[dict[str, str]]]:
    """Separate readable candidates from missing files without stopping a batch."""
    available = []
    errors = []
    for record in records:
        if record.image_path.is_file():
            available.append(record)
        else:
            errors.append(
                {
                    "doc_id": record.doc_id,
                    "page_index": str(record.page_index),
                    "image_path": str(record.image_path),
                    "error": "Page image does not exist",
                }
            )
    return available, errors
