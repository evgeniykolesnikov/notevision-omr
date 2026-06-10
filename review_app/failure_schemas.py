"""Validation for failed OMR page classifications."""

from __future__ import annotations

from typing import Mapping

from review_app.models import (
    CLASSIFIER_ERROR_TYPES,
    CORRECTED_PAGE_TYPES,
    FAILURE_DECISIONS,
    FAILURE_REASONS,
    TRISTATE_VALUES,
)


def validate_failure_submission(
    form: Mapping[str, str],
    *,
    reviewed: bool,
) -> tuple[dict[str, str], list[str]]:
    """Normalize a failure form and validate controlled vocabularies."""
    failure_reason = str(form.get("failure_reason", "")).strip()
    decision = str(form.get("decision", "")).strip()
    corrected_page_type = str(form.get("corrected_page_type", "")).strip()
    corrected_has_music = str(form.get("corrected_has_music", "")).strip()
    should_send_to_omr = str(form.get("should_send_to_omr", "")).strip()
    classifier_error_type = str(form.get("classifier_error_type", "")).strip()
    errors: list[str] = []

    if failure_reason not in FAILURE_REASONS:
        errors.append("Choose a valid failure reason.")
        failure_reason = "unknown_failure"
    if decision and decision not in FAILURE_DECISIONS:
        errors.append("Choose a valid decision.")
        decision = ""
    if reviewed and not decision:
        errors.append("Choose a decision before marking the review complete.")
    if corrected_page_type and corrected_page_type not in CORRECTED_PAGE_TYPES:
        errors.append("Choose a valid corrected page type.")
        corrected_page_type = ""
    if corrected_has_music and corrected_has_music not in TRISTATE_VALUES:
        errors.append("Choose a valid corrected has_music value.")
        corrected_has_music = ""
    if should_send_to_omr and should_send_to_omr not in TRISTATE_VALUES:
        errors.append("Choose a valid OMR routing value.")
        should_send_to_omr = ""
    if (
        classifier_error_type
        and classifier_error_type not in CLASSIFIER_ERROR_TYPES
    ):
        errors.append("Choose a valid classifier error type.")
        classifier_error_type = ""

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
            "corrected_page_type": corrected_page_type,
            "corrected_has_music": corrected_has_music,
            "should_send_to_omr": should_send_to_omr,
            "classifier_error_type": classifier_error_type,
        },
        errors,
    )
