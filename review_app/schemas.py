"""Validation helpers for expert review forms."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Mapping

from review_app.models import COUNTER_FIELDS, PAGE_USABLE_VALUES, PROBLEM_FIELDS


@dataclass
class ReviewSubmission:
    reviewer: str
    review_date: str
    checked_measures: int
    correct_measures: int
    reference_notes: int
    matched_notes: int
    pitch_errors: int
    duration_errors: int
    missing_notes: int
    extra_notes: int
    voice_errors: int
    measure_errors: int
    page_usable: str
    usability_score: int
    pitch_problem: int
    rhythm_problem: int
    missing_notes_problem: int
    extra_notes_problem: int
    chord_problem: int
    voice_problem: int
    measure_structure_problem: int
    playback_problem: int
    unreadable_or_failed: int
    dominant_error: str
    expert_comment: str
    requires_new_omr: int

    def as_dict(self) -> dict[str, object]:
        return {
            field: getattr(self, field)
            for field in self.__dataclass_fields__
        }


def resolve_review_metadata(
    reviewer: str,
    *,
    complete: bool,
    existing_review_date: str = "",
    today: date | None = None,
) -> tuple[str, str]:
    """Return reviewer and the automatic completion date."""
    review_date = (
        (today or date.today()).isoformat()
        if complete
        else existing_review_date
    )
    return reviewer.strip(), review_date


def _parse_non_negative_int(
    form: Mapping[str, str],
    field: str,
    errors: list[str],
) -> int:
    raw_value = str(form.get(field, "")).strip()
    if raw_value == "":
        return 0
    try:
        value = int(raw_value)
    except ValueError:
        errors.append(f"Поле {field} должно быть целым числом.")
        return 0
    if value < 0:
        errors.append(f"Поле {field} не может быть отрицательным.")
        return 0
    return value


def validate_review_submission(
    form: Mapping[str, str],
    *,
    complete: bool,
    reviewer: str = "",
    review_date: str = "",
) -> tuple[ReviewSubmission, list[str]]:
    """Parse a form and return normalized values with validation errors."""
    errors: list[str] = []
    counters = {
        field: _parse_non_negative_int(form, field, errors)
        for field in COUNTER_FIELDS
    }
    page_usable = str(form.get("page_usable", "")).strip()
    raw_usability_score = str(form.get("usability_score", "")).strip()
    usability_score = 0
    if raw_usability_score:
        try:
            usability_score = int(raw_usability_score)
        except ValueError:
            errors.append("Общая оценка должна быть целым числом от 1 до 5.")
        else:
            if usability_score < 1 or usability_score > 5:
                errors.append("Общая оценка должна быть от 1 до 5.")
    if page_usable and page_usable not in PAGE_USABLE_VALUES:
        errors.append("Пригодность может быть только yes, partial или no.")
    if (
        str(form.get("correct_measures", "")).strip()
        and str(form.get("checked_measures", "")).strip()
        and counters["correct_measures"] > counters["checked_measures"]
    ):
        errors.append(
            "Число корректных тактов не может превышать число проверенных."
        )
    if (
        str(form.get("matched_notes", "")).strip()
        and str(form.get("reference_notes", "")).strip()
        and counters["matched_notes"] > counters["reference_notes"]
    ):
        errors.append(
            "Число сопоставленных нот не может превышать число эталонных."
        )
    if complete:
        if not reviewer:
            errors.append("Имя эксперта отсутствует в текущей сессии.")
        if not page_usable:
            errors.append("Для завершения проверки укажите пригодность.")

    problems = {
        field: 1
        if str(form.get(field, "")).lower() in {"1", "true", "on", "yes"}
        else 0
        for field in PROBLEM_FIELDS
    }
    submission = ReviewSubmission(
        reviewer=reviewer,
        review_date=review_date,
        **counters,
        page_usable=page_usable,
        usability_score=usability_score,
        **problems,
        dominant_error=str(form.get("dominant_error", "")).strip(),
        expert_comment=str(form.get("expert_comment", "")).strip(),
        requires_new_omr=1
        if str(form.get("requires_new_omr", "")).lower()
        in {"1", "true", "on", "yes"}
        else 0,
    )
    return submission, errors
