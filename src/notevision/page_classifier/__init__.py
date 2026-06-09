"""Trainable page-classification baselines for NoteVision OMR."""

from .dataset import MANUAL_SOURCES, PageRecord, build_page_records, split_by_document

__all__ = [
    "MANUAL_SOURCES",
    "PageRecord",
    "build_page_records",
    "split_by_document",
]
