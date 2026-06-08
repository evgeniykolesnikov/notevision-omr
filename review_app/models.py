"""Database field definitions shared by the review application."""

REVIEW_STATUSES = ("not_reviewed", "draft", "completed")
PAGE_USABLE_VALUES = ("yes", "partial", "no")

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
    "doc_id",
    "page_index",
    "reviewer_id",
    "reviewer",
    "review_date",
    *COUNTER_FIELDS,
    "page_usable",
    "dominant_error",
    "expert_comment",
    "requires_new_omr",
    "review_status",
    "updated_at",
    "usability_score",
    *PROBLEM_FIELDS,
)
