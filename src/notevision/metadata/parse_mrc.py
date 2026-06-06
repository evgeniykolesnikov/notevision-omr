"""Read bibliographic metadata from MARC/MRC files."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Union

from pymarc import MARCReader, Record

PathLike = Union[str, Path]

METADATA_FIELDS = [
    "doc_id",
    "mrc_path",
    "title",
    "authors",
    "year",
    "language",
    "publication",
    "physical_description",
    "subjects",
    "record_id",
    "electronic_resources",
    "raw_fields_summary",
]


def find_mrc_in_document_dir(document_dir: PathLike) -> Path:
    """Return the only MRC file located directly in a document directory."""
    directory = Path(document_dir)
    if directory.is_dir():
        mrc_files = sorted(
            (
                path
                for path in directory.iterdir()
                if path.is_file() and path.suffix.lower() == ".mrc"
            ),
            key=lambda path: path.name.lower(),
        )
    else:
        mrc_files = []

    if not mrc_files:
        raise FileNotFoundError(f"No MRC file found in document directory: {directory}")
    if len(mrc_files) > 1:
        found_files = ", ".join(str(path) for path in mrc_files)
        raise ValueError(
            f"Multiple MRC files found in document directory {directory}: "
            f"{found_files}"
        )

    return mrc_files[0]


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split()).strip(" /:;,")
    return cleaned or None


def _field_values(
    record: Record,
    tags: tuple[str, ...],
    subfield_codes: tuple[str, ...] | None = None,
) -> list[str]:
    values: list[str] = []
    for field in record.get_fields(*tags):
        if subfield_codes is None:
            value = _clean(field.value())
        else:
            value = _clean(" ".join(field.get_subfields(*subfield_codes)))
        if value:
            values.append(value)
    return values


def _first(values: list[str]) -> str | None:
    return values[0] if values else None


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _extract_year(record: Record) -> str | None:
    publication_dates = _field_values(record, ("264",), ("c",))
    if not publication_dates:
        publication_dates = _field_values(record, ("260",), ("c",))

    for value in publication_dates:
        match = re.search(r"(?<!\d)(1[0-9]{3}|20[0-9]{2})(?!\d)", value)
        if match:
            return match.group(1)

    control_008 = record.get("008")
    if control_008:
        data = control_008.value()
        if len(data) >= 11 and data[7:11].isdigit():
            return data[7:11]
    return None


def _extract_language(record: Record) -> str | None:
    language = _first(_field_values(record, ("041",), ("a",)))
    if language:
        return language

    control_008 = record.get("008")
    if control_008:
        data = control_008.value()
        if len(data) >= 38:
            code = data[35:38].strip()
            if code and code != "|||":
                return code
    return None


def _raw_fields_summary(record: Record) -> dict[str, list[str]]:
    summary: defaultdict[str, list[str]] = defaultdict(list)
    for field in record.fields:
        value = _clean(field.value())
        if value:
            summary[field.tag].append(value)
    return dict(summary)


def parse_mrc_file(mrc_path: PathLike, doc_id: str | None = None) -> dict[str, Any]:
    """Parse the first MARC record in an MRC file into normalized metadata."""
    source = Path(mrc_path)
    if not source.exists():
        raise FileNotFoundError(f"MRC file does not exist: {source}")
    if not source.is_file():
        raise ValueError(f"MRC path is not a file: {source}")

    record: Record | None = None
    with source.open("rb") as mrc_file:
        reader = MARCReader(
            mrc_file,
            to_unicode=True,
            utf8_handling="replace",
            permissive=True,
        )
        for candidate in reader:
            if candidate is not None:
                record = candidate
                break

    if record is None:
        raise ValueError(f"No readable MARC record found in MRC file: {source}")

    title = _first(_field_values(record, ("245",), ("a", "b", "n", "p")))
    authors = _unique(
        _field_values(
            record,
            ("100", "110", "111", "700", "710", "711"),
        )
    )
    publication = _first(_field_values(record, ("264",)))
    if publication is None:
        publication = _first(_field_values(record, ("260",)))

    electronic_resources: list[str] = []
    for field in record.get_fields("856"):
        electronic_resources.extend(
            value
            for value in (_clean(url) for url in field.get_subfields("u"))
            if value
        )

    return {
        "doc_id": doc_id if doc_id is not None else source.resolve().parent.name,
        "mrc_path": str(source),
        "title": title,
        "authors": authors,
        "year": _extract_year(record),
        "language": _extract_language(record),
        "publication": publication,
        "physical_description": _first(_field_values(record, ("300",))),
        "subjects": _unique(
            _field_values(
                record,
                ("600", "610", "611", "630", "648", "650", "651", "653"),
            )
        ),
        "record_id": _first(_field_values(record, ("001",))),
        "electronic_resources": _unique(electronic_resources),
        "raw_fields_summary": _raw_fields_summary(record),
    }
