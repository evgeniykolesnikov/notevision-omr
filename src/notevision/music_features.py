"""Extract conservative music-theoretical features from MusicXML/MXL files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Iterable

FEATURE_COLUMNS = [
    "doc_id",
    "page_index",
    "source_file",
    "extraction_status",
    "key_signature",
    "key_fifths",
    "mode",
    "key_name_latin",
    "key_name_ru",
    "time_signature",
    "clefs",
    "parts_count",
    "part_names",
    "instruments",
    "confidence",
    "source",
    "error",
]

MAJOR_KEYS = {
    -7: ("Cb-dur", "до-бемоль мажор"),
    -6: ("Gb-dur", "соль-бемоль мажор"),
    -5: ("Db-dur", "ре-бемоль мажор"),
    -4: ("Ab-dur", "ля-бемоль мажор"),
    -3: ("Eb-dur", "ми-бемоль мажор"),
    -2: ("Bb-dur", "си-бемоль мажор"),
    -1: ("F-dur", "фа мажор"),
    0: ("C-dur", "до мажор"),
    1: ("G-dur", "соль мажор"),
    2: ("D-dur", "ре мажор"),
    3: ("A-dur", "ля мажор"),
    4: ("E-dur", "ми мажор"),
    5: ("B-dur", "си мажор"),
    6: ("F#-dur", "фа-диез мажор"),
    7: ("C#-dur", "до-диез мажор"),
}

MINOR_KEYS = {
    -7: ("ab-moll", "ля-бемоль минор"),
    -6: ("eb-moll", "ми-бемоль минор"),
    -5: ("bb-moll", "си-бемоль минор"),
    -4: ("f-moll", "фа минор"),
    -3: ("c-moll", "до минор"),
    -2: ("g-moll", "соль минор"),
    -1: ("d-moll", "ре минор"),
    0: ("a-moll", "ля минор"),
    1: ("e-moll", "ми минор"),
    2: ("b-moll", "си минор"),
    3: ("f#-moll", "фа-диез минор"),
    4: ("c#-moll", "до-диез минор"),
    5: ("g#-moll", "соль-диез минор"),
    6: ("d#-moll", "ре-диез минор"),
    7: ("a#-moll", "ля-диез минор"),
}

CLEF_NAMES_RU = {
    "treble": "скрипичный",
    "bass": "басовый",
    "alto": "альтовый",
    "tenor": "теноровый",
}


def _unique(values: Iterable[object]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def identify_musicxml_page(path: Path) -> tuple[str, str, str]:
    """Infer ``doc_id`` and page index from established project path names."""
    resolved = Path(path)
    doc_id = next(
        (
            part
            for part in reversed(resolved.parts)
            if re.fullmatch(r"rsl\d+", part, re.IGNORECASE)
        ),
        "unknown",
    )
    page_match = re.search(r"page_(\d+)", resolved.stem, re.IGNORECASE)
    if page_match is None:
        page_match = next(
            (
                match
                for part in reversed(resolved.parts)
                if (match := re.search(r"page_(\d+)", part, re.IGNORECASE))
            ),
            None,
        )
    page_index = str(int(page_match.group(1))) if page_match else "unknown"
    errors = []
    if doc_id == "unknown":
        errors.append("Could not infer doc_id from path")
    if page_index == "unknown":
        errors.append("Could not infer page_index from path")
    return doc_id, page_index, "; ".join(errors)


def key_names(fifths: int, mode: str) -> tuple[str, str]:
    """Return German/Latin and Russian names without inferring an absent mode."""
    if mode == "major":
        return MAJOR_KEYS.get(fifths, ("unknown", "unknown"))
    if mode == "minor":
        return MINOR_KEYS.get(fifths, ("unknown", "unknown"))
    major = MAJOR_KEYS.get(fifths)
    minor = MINOR_KEYS.get(fifths)
    if major and minor:
        return (
            f"{major[0]} / {minor[0]}",
            f"{major[1]} / {minor[1]}",
        )
    return "unknown", "unknown"


def _key_signature_text(fifths: int) -> str:
    if fifths == 0:
        return "0"
    accidental = "sharp" if fifths > 0 else "flat"
    return f"{abs(fifths)} {accidental}{'' if abs(fifths) == 1 else 's'}"


def _clef_name(value: Any) -> str:
    class_name = value.__class__.__name__.lower()
    if "treble" in class_name:
        return CLEF_NAMES_RU["treble"]
    if "bass" in class_name:
        return CLEF_NAMES_RU["bass"]
    if "alto" in class_name:
        return CLEF_NAMES_RU["alto"]
    if "tenor" in class_name:
        return CLEF_NAMES_RU["tenor"]
    sign = str(getattr(value, "sign", "") or "").upper()
    line = getattr(value, "line", None)
    if sign == "G":
        return CLEF_NAMES_RU["treble"]
    if sign == "F":
        return CLEF_NAMES_RU["bass"]
    if sign == "C" and line == 3:
        return CLEF_NAMES_RU["alto"]
    if sign == "C" and line == 4:
        return CLEF_NAMES_RU["tenor"]
    return str(value)


def _base_row(path: Path) -> dict[str, object]:
    doc_id, page_index, path_error = identify_musicxml_page(path)
    return {
        "doc_id": doc_id,
        "page_index": page_index,
        "source_file": str(path),
        "extraction_status": "failed",
        "key_signature": "unknown",
        "key_fifths": "unknown",
        "mode": "unknown",
        "key_name_latin": "unknown",
        "key_name_ru": "unknown",
        "time_signature": "unknown",
        "clefs": "unknown",
        "parts_count": 0,
        "part_names": "unknown",
        "instruments": "unknown",
        "confidence": "low",
        "source": "not_found",
        "error": path_error,
    }


def extract_music_features(
    source_file: Path,
    *,
    parser: Callable[[str], Any] | None = None,
) -> dict[str, object]:
    """Extract explicit MusicXML metadata from one score without guessing."""
    path = Path(source_file)
    row = _base_row(path)
    if not path.is_file():
        row["error"] = _join_errors(str(row["error"]), f"File not found: {path}")
        return row

    try:
        if parser is None:
            from music21 import converter

            parser = converter.parse
        score = parser(str(path))
        if score is None:
            raise ValueError("MusicXML parser returned no score")

        from music21 import clef, instrument, key, meter

        keys = list(score.recurse().getElementsByClass(key.Key))
        signatures = list(score.recurse().getElementsByClass(key.KeySignature))
        selected_key = keys[0] if keys else signatures[0] if signatures else None
        if selected_key is not None:
            fifths = int(selected_key.sharps)
            mode = str(getattr(selected_key, "mode", "") or "unknown").lower()
            latin, russian = key_names(fifths, mode)
            row.update(
                {
                    "key_signature": _key_signature_text(fifths),
                    "key_fifths": fifths,
                    "mode": mode,
                    "key_name_latin": latin,
                    "key_name_ru": russian,
                    "confidence": "high",
                    "source": "musicxml",
                }
            )

        time_signatures = _unique(
            value.ratioString
            for value in score.recurse().getElementsByClass(meter.TimeSignature)
        )
        clefs = _unique(
            _clef_name(value)
            for value in score.recurse().getElementsByClass(clef.Clef)
        )
        parts = list(score.parts)
        source_part_ids = {
            re.sub(r"-Staff\d+$", "", str(getattr(part, "id", "") or ""))
            for part in parts
        }
        source_part_ids.discard("")
        part_names = _unique(getattr(part, "partName", "") for part in parts)
        instrument_names: list[str] = []
        for part in parts:
            found = list(part.recurse().getElementsByClass(instrument.Instrument))
            instrument_names.extend(
                str(getattr(value, "instrumentName", "") or "")
                or str(getattr(value, "partName", "") or "")
                for value in found
            )

        row.update(
            {
                "time_signature": ";".join(time_signatures) or "unknown",
                "clefs": ";".join(clefs) or "unknown",
                "parts_count": len(source_part_ids) or len(parts),
                "part_names": ";".join(part_names) or "unknown",
                "instruments": ";".join(_unique(instrument_names)) or "unknown",
            }
        )
        other_features_found = bool(
            time_signatures or clefs or part_names or instrument_names or parts
        )
        key_found = selected_key is not None
        row["extraction_status"] = (
            "success" if key_found and other_features_found
            else "partial" if key_found or other_features_found
            else "failed"
        )
        if not key_found:
            row["source"] = "not_found"
            row["confidence"] = "low"
        if row["extraction_status"] == "failed":
            row["error"] = _join_errors(
                str(row["error"]),
                "No supported music features found",
            )
    except Exception as error:
        row["extraction_status"] = "failed"
        row["error"] = _join_errors(str(row["error"]), str(error))
    return row


def _join_errors(*values: str) -> str:
    return "; ".join(value for value in values if value)


def find_musicxml_files(directory: Path, *, recursive: bool = False) -> list[Path]:
    """Find MXL and uncompressed MusicXML files deterministically."""
    if not directory.is_dir():
        raise FileNotFoundError(f"MusicXML directory does not exist: {directory}")
    iterator = directory.rglob("*") if recursive else directory.glob("*")
    return sorted(
        (
            path
            for path in iterator
            if path.is_file()
            and path.suffix.lower() in {".mxl", ".musicxml", ".xml"}
        ),
        key=lambda path: str(path).lower(),
    )
