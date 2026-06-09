"""Normalize legacy and thesis OMR candidate tables."""

from __future__ import annotations

import pandas as pd

BASE_COLUMNS = {"doc_id", "page_index"}
LEGACY_COLUMNS = {"preprocessed_path", "exists"}
THESIS_BASE_COLUMNS = {"image_path", "page_type"}
THESIS_MUSIC_COLUMNS = {"has_music", "has_music_manual"}

NORMALIZED_INPUT_PATH = "_candidate_input_path"
NORMALIZED_EXISTS = "_candidate_exists"
NORMALIZED_INPUT_KIND = "_candidate_input_kind"
NORMALIZED_SELECTED = "_candidate_selected"

MUSIC_PAGE_TYPES = {"music", "mixed"}


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _binary_music(value: object) -> bool:
    try:
        return int(float(str(value).strip())) == 1
    except ValueError:
        return False


def _nonempty(value: object) -> bool:
    if pd.isna(value):
        return False
    return bool(str(value).strip())


def adapt_omr_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    """Add normalized path and selection fields for supported CSV formats.

    Legacy rows use ``preprocessed_path`` and ``exists``. Thesis rows use
    ``image_path`` and are eligible when ``has_music == 1`` and ``page_type``
    is ``music`` or ``mixed``. In a mixed table, a non-empty legacy path takes
    precedence for that row; otherwise the image path is used directly.
    """
    missing_base = BASE_COLUMNS.difference(candidates.columns)
    if missing_base:
        raise ValueError(
            "Candidates are missing required columns: "
            + ", ".join(sorted(missing_base))
        )

    supports_legacy = LEGACY_COLUMNS.issubset(candidates.columns)
    supports_thesis = (
        THESIS_BASE_COLUMNS.issubset(candidates.columns)
        and bool(THESIS_MUSIC_COLUMNS.intersection(candidates.columns))
    )
    if not supports_legacy and not supports_thesis:
        raise ValueError(
            "Candidates must use either the legacy columns "
            "(exists, preprocessed_path) or the thesis columns "
            "(image_path, page_type, has_music or has_music_manual)"
        )

    normalized = candidates.copy()
    input_paths: list[str] = []
    exists_values: list[bool] = []
    input_kinds: list[str] = []
    selected_values: list[bool] = []

    for row in normalized.to_dict(orient="records"):
        legacy_path = (
            str(row.get("preprocessed_path", "")).strip()
            if supports_legacy
            else ""
        )
        image_path = (
            str(row.get("image_path", "")).strip()
            if supports_thesis
            else ""
        )

        if _nonempty(legacy_path):
            input_paths.append(legacy_path)
            exists = _truthy(row.get("exists", False))
            exists_values.append(exists)
            input_kinds.append("preprocessed")
            selected_values.append(True)
            continue

        if _nonempty(image_path):
            has_music_value = row.get(
                "has_music",
                row.get("has_music_manual", ""),
            )
            is_evaluation_sample = _nonempty(row.get("sample_group", ""))
            eligible = is_evaluation_sample or (
                _binary_music(has_music_value)
                and str(row.get("page_type", "")).strip().lower()
                in MUSIC_PAGE_TYPES
            )
            input_paths.append(image_path)
            exists_values.append(eligible)
            input_kinds.append("image_path")
            selected_values.append(eligible)
            continue

        input_paths.append("")
        exists_values.append(False)
        input_kinds.append("unknown")
        selected_values.append(False)

    normalized[NORMALIZED_INPUT_PATH] = input_paths
    normalized[NORMALIZED_EXISTS] = exists_values
    normalized[NORMALIZED_INPUT_KIND] = input_kinds
    normalized[NORMALIZED_SELECTED] = selected_values
    return normalized
