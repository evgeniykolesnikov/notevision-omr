"""Validation for failed OMR page classifications."""

from __future__ import annotations

from typing import Mapping

from review_app.models import FAILURE_DECISIONS, FAILURE_REASONS


def validate_failure_submission(
    form: Mapping[str, str],
    *,
    reviewed: bool,
) -> tuple[dict[str, str], list[str]]:
    """Normalize a failure form and validate controlled vocabularies."""
    failure_reason = str(form.get("failure_reason", "")).strip()
    decision = str(form.get("decision", "")).strip()
    errors: list[str] = []
    if failure_reason not in FAILURE_REASONS:
        errors.append("Выберите допустимую причину сбоя.")
        failure_reason = "unknown_failure"
    if decision and decision not in FAILURE_DECISIONS:
        errors.append("Выберите допустимое решение.")
        decision = ""
    if reviewed and not decision:
        errors.append("Для завершения разбора выберите решение.")
    return (
        {
            "failure_reason": failure_reason,
            "image_quality_issue": str(
                form.get("image_quality_issue", "")
            ).strip(),
            "decision": decision,
            "audiveris_log_excerpt": str(
                form.get("audiveris_log_excerpt", "")
            ).strip(),
            "expert_comment": str(form.get("expert_comment", "")).strip(),
        },
        errors,
    )
