"""Database field definitions shared by the review application."""

REVIEW_STATUSES = ("not_reviewed", "draft", "completed")
PAGE_USABLE_VALUES = ("yes", "partial", "no")
FAILURE_REASONS = (
    "small_interline",
    "invalid_image",
    "low_contrast",
    "cropped",
    "rotated_or_perspective",
    "mixed_layout",
    "handwritten_notation",
    "audiveris_process_error",
    "timeout",
    "musicxml_export_error",
    "unknown_failure",
)
FAILURE_DECISIONS = (
    "retry_same",
    "retry_preprocessed",
    "retry_400dpi",
    "exclude_from_omr",
    "requires_manual_review",
    "accepted_failure",
)
FAILURE_REVIEW_STATUSES = ("draft", "reviewed")
FAILURE_EXPORT_FIELDS = (
    "doc_id",
    "page_index",
    "page_type",
    "failure_status",
    "failure_reason",
    "image_quality_issue",
    "decision",
    "audiveris_log_excerpt",
    "expert_comment",
    "review_status",
    "updated_at",
    "fallback_400_status",
    "fallback_400_mxl_path",
    "fallback_400_midi_path",
    "fallback_400_runtime_seconds",
    "fallback_400_error",
    "preprocessing_fallback_status",
    "preprocessing_best_variant",
    "preprocessing_mxl_path",
    "preprocessing_midi_path",
    "preprocessing_runtime_seconds",
    "preprocessing_error",
)

COUNTER_FIELDS = (
    "checked_measures",
    "correct_measures",
    "reference_notes",
    "matched_notes",
    "pitch_errors",
    "duration_errors",
    "missing_notes",
    "extra_notes",
    "voice_errors",
    "measure_errors",
)

PROBLEM_FIELDS = (
    "pitch_problem",
    "rhythm_problem",
    "missing_notes_problem",
    "extra_notes_problem",
    "chord_problem",
    "voice_problem",
    "measure_structure_problem",
    "playback_problem",
    "unreadable_or_failed",
)

REVIEW_FIELDS = (
    "reviewer",
    "review_date",
    *COUNTER_FIELDS,
    "page_usable",
    "usability_score",
    *PROBLEM_FIELDS,
    "dominant_error",
    "expert_comment",
    "requires_new_omr",
)

EXPORT_FIELDS = (
    "review_id",
    "item_number",
    "doc_id",
    "page_index",
    "reviewer_id",
    "reviewer",
    "review_status",
    "review_date",
    "page_usable",
    "usability_score",
    *PROBLEM_FIELDS,
    "dominant_error",
    "expert_comment",
    "requires_new_omr",
    *COUNTER_FIELDS,
    "updated_at",
)
