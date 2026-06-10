"""SQLite persistence for review items, reviewers, and assessments."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Iterable

from review_app.models import REAL_OMR_FAILURE_REASONS, REVIEW_FIELDS

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "review_app.db"
LOCAL_REVIEWER_NAME = "local"

REVIEW_COLUMN_SQL = """
    review_status TEXT NOT NULL DEFAULT 'not_reviewed'
        CHECK(review_status IN ('not_reviewed', 'draft', 'completed')),
    reviewer TEXT NOT NULL DEFAULT '',
    review_date TEXT NOT NULL DEFAULT '',
    checked_measures INTEGER NOT NULL DEFAULT 0,
    correct_measures INTEGER NOT NULL DEFAULT 0,
    reference_notes INTEGER NOT NULL DEFAULT 0,
    matched_notes INTEGER NOT NULL DEFAULT 0,
    pitch_errors INTEGER NOT NULL DEFAULT 0,
    duration_errors INTEGER NOT NULL DEFAULT 0,
    missing_notes INTEGER NOT NULL DEFAULT 0,
    extra_notes INTEGER NOT NULL DEFAULT 0,
    voice_errors INTEGER NOT NULL DEFAULT 0,
    measure_errors INTEGER NOT NULL DEFAULT 0,
    page_usable TEXT NOT NULL DEFAULT '',
    usability_score INTEGER NOT NULL DEFAULT 0,
    pitch_problem INTEGER NOT NULL DEFAULT 0,
    rhythm_problem INTEGER NOT NULL DEFAULT 0,
    missing_notes_problem INTEGER NOT NULL DEFAULT 0,
    extra_notes_problem INTEGER NOT NULL DEFAULT 0,
    chord_problem INTEGER NOT NULL DEFAULT 0,
    voice_problem INTEGER NOT NULL DEFAULT 0,
    measure_structure_problem INTEGER NOT NULL DEFAULT 0,
    playback_problem INTEGER NOT NULL DEFAULT 0,
    unreadable_or_failed INTEGER NOT NULL DEFAULT 0,
    dominant_error TEXT NOT NULL DEFAULT '',
    expert_comment TEXT NOT NULL DEFAULT '',
    requires_new_omr INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
"""

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS review_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_number INTEGER NOT NULL UNIQUE,
    doc_id TEXT NOT NULL,
    page_index INTEGER NOT NULL,
    scan_path TEXT NOT NULL,
    audio_path TEXT NOT NULL,
    track_paths TEXT NOT NULL DEFAULT '[]',
    review_set TEXT NOT NULL DEFAULT 'default',
    {REVIEW_COLUMN_SQL}
);

CREATE TABLE IF NOT EXISTS reviewers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL DEFAULT '',
    access_token TEXT UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_item_id INTEGER NOT NULL REFERENCES review_items(id),
    reviewer_id INTEGER NOT NULL REFERENCES reviewers(id),
    {REVIEW_COLUMN_SQL},
    UNIQUE(review_item_id, reviewer_id)
);

CREATE INDEX IF NOT EXISTS idx_reviews_reviewer
    ON reviews(reviewer_id, review_status);

CREATE TABLE IF NOT EXISTS failure_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL,
    page_index INTEGER NOT NULL,
    page_type TEXT NOT NULL DEFAULT '',
    has_music_manual TEXT NOT NULL DEFAULT '',
    cnn_prediction TEXT NOT NULL DEFAULT '',
    classical_prediction TEXT NOT NULL DEFAULT '',
    sample_group TEXT NOT NULL DEFAULT '',
    source_reason TEXT NOT NULL DEFAULT '',
    image_path TEXT NOT NULL,
    omr_dir TEXT NOT NULL,
    log_path TEXT NOT NULL DEFAULT '',
    failure_status TEXT NOT NULL DEFAULT 'missing_mxl',
    failure_reason TEXT NOT NULL DEFAULT 'unknown_failure',
    image_quality_issue TEXT NOT NULL DEFAULT '',
    decision TEXT NOT NULL DEFAULT '',
    audiveris_log_excerpt TEXT NOT NULL DEFAULT '',
    expert_comment TEXT NOT NULL DEFAULT '',
    corrected_page_type TEXT NOT NULL DEFAULT '',
    corrected_has_music TEXT NOT NULL DEFAULT '',
    should_send_to_omr TEXT NOT NULL DEFAULT '',
    classifier_error_type TEXT NOT NULL DEFAULT '',
    reviewer TEXT NOT NULL DEFAULT '',
    review_status TEXT NOT NULL DEFAULT 'draft'
        CHECK(review_status IN ('draft', 'reviewed')),
    updated_at TEXT,
    fallback_400_status TEXT NOT NULL DEFAULT '',
    fallback_400_mxl_path TEXT NOT NULL DEFAULT '',
    fallback_400_midi_path TEXT NOT NULL DEFAULT '',
    fallback_400_runtime_seconds REAL,
    fallback_400_error TEXT NOT NULL DEFAULT '',
    preprocessing_fallback_status TEXT NOT NULL DEFAULT '',
    preprocessing_best_variant TEXT NOT NULL DEFAULT '',
    preprocessing_mxl_path TEXT NOT NULL DEFAULT '',
    preprocessing_midi_path TEXT NOT NULL DEFAULT '',
    preprocessing_runtime_seconds REAL,
    preprocessing_error TEXT NOT NULL DEFAULT '',
    UNIQUE(doc_id, page_index)
);

CREATE INDEX IF NOT EXISTS idx_failure_reviews_status
    ON failure_reviews(review_status, failure_reason);
"""

LEGACY_MIGRATION_COLUMNS = {
    "usability_score": "INTEGER NOT NULL DEFAULT 0",
    "pitch_problem": "INTEGER NOT NULL DEFAULT 0",
    "rhythm_problem": "INTEGER NOT NULL DEFAULT 0",
    "missing_notes_problem": "INTEGER NOT NULL DEFAULT 0",
    "extra_notes_problem": "INTEGER NOT NULL DEFAULT 0",
    "chord_problem": "INTEGER NOT NULL DEFAULT 0",
    "voice_problem": "INTEGER NOT NULL DEFAULT 0",
    "measure_structure_problem": "INTEGER NOT NULL DEFAULT 0",
    "playback_problem": "INTEGER NOT NULL DEFAULT 0",
    "unreadable_or_failed": "INTEGER NOT NULL DEFAULT 0",
}

REVIEWER_MIGRATION_COLUMNS = {
    "normalized_name": "TEXT NOT NULL DEFAULT ''",
    "updated_at": "TEXT",
}

ITEM_MIGRATION_COLUMNS = {
    "review_set": "TEXT NOT NULL DEFAULT 'default'",
}

FAILURE_MIGRATION_COLUMNS = {
    "has_music_manual": "TEXT NOT NULL DEFAULT ''",
    "cnn_prediction": "TEXT NOT NULL DEFAULT ''",
    "classical_prediction": "TEXT NOT NULL DEFAULT ''",
    "sample_group": "TEXT NOT NULL DEFAULT ''",
    "source_reason": "TEXT NOT NULL DEFAULT ''",
    "corrected_page_type": "TEXT NOT NULL DEFAULT ''",
    "corrected_has_music": "TEXT NOT NULL DEFAULT ''",
    "should_send_to_omr": "TEXT NOT NULL DEFAULT ''",
    "classifier_error_type": "TEXT NOT NULL DEFAULT ''",
    "fallback_400_status": "TEXT NOT NULL DEFAULT ''",
    "fallback_400_mxl_path": "TEXT NOT NULL DEFAULT ''",
    "fallback_400_midi_path": "TEXT NOT NULL DEFAULT ''",
    "fallback_400_runtime_seconds": "REAL",
    "fallback_400_error": "TEXT NOT NULL DEFAULT ''",
    "preprocessing_fallback_status": "TEXT NOT NULL DEFAULT ''",
    "preprocessing_best_variant": "TEXT NOT NULL DEFAULT ''",
    "preprocessing_mxl_path": "TEXT NOT NULL DEFAULT ''",
    "preprocessing_midi_path": "TEXT NOT NULL DEFAULT ''",
    "preprocessing_runtime_seconds": "REAL",
    "preprocessing_error": "TEXT NOT NULL DEFAULT ''",
}


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def normalize_reviewer_name(name: str) -> str:
    return " ".join(name.split()).casefold()


def _migrate_reviewers(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        "SELECT id, name FROM reviewers ORDER BY id"
    ).fetchall()
    keepers: dict[str, int] = {}
    for row in rows:
        normalized_name = normalize_reviewer_name(str(row["name"]))
        if not normalized_name:
            normalized_name = f"reviewer-{row['id']}"
        keeper_id = keepers.get(normalized_name)
        if keeper_id is None:
            keepers[normalized_name] = int(row["id"])
            connection.execute(
                """
                UPDATE reviewers
                SET normalized_name = ?,
                    updated_at = COALESCE(updated_at, created_at)
                WHERE id = ?
                """,
                (normalized_name, row["id"]),
            )
            continue

        duplicate_reviews = connection.execute(
            "SELECT * FROM reviews WHERE reviewer_id = ?",
            (row["id"],),
        ).fetchall()
        for review in duplicate_reviews:
            existing = connection.execute(
                """
                SELECT id FROM reviews
                WHERE review_item_id = ? AND reviewer_id = ?
                """,
                (review["review_item_id"], keeper_id),
            ).fetchone()
            if existing is None:
                connection.execute(
                    "UPDATE reviews SET reviewer_id = ? WHERE id = ?",
                    (keeper_id, review["id"]),
                )
        connection.execute(
            "DELETE FROM reviews WHERE reviewer_id = ?",
            (row["id"],),
        )
        connection.execute("DELETE FROM reviewers WHERE id = ?", (row["id"],))

    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_reviewers_normalized_name
        ON reviewers(normalized_name)
        """
    )


def _ensure_local_reviewer(connection: sqlite3.Connection) -> int:
    normalized_name = normalize_reviewer_name(LOCAL_REVIEWER_NAME)
    row = connection.execute(
        "SELECT id FROM reviewers WHERE normalized_name = ?",
        (normalized_name,),
    ).fetchone()
    if row:
        return int(row["id"])
    cursor = connection.execute(
        """
        INSERT INTO reviewers (name, normalized_name, access_token)
        VALUES (?, ?, NULL)
        """,
        (LOCAL_REVIEWER_NAME, normalized_name),
    )
    return int(cursor.lastrowid)


def _migrate_legacy_reviews(connection: sqlite3.Connection) -> None:
    local_reviewer_id = _ensure_local_reviewer(connection)
    fields = ", ".join(REVIEW_FIELDS)
    placeholders = ", ".join("?" for _ in REVIEW_FIELDS)
    legacy_rows = connection.execute(
        """
        SELECT * FROM review_items
        WHERE review_status != 'not_reviewed'
           OR reviewer != ''
           OR updated_at IS NOT NULL
        """
    ).fetchall()
    for row in legacy_rows:
        values = [row[field] for field in REVIEW_FIELDS]
        connection.execute(
            f"""
            INSERT OR IGNORE INTO reviews (
                review_item_id, reviewer_id, {fields},
                review_status, updated_at
            ) VALUES (?, ?, {placeholders}, ?, ?)
            """,
            (
                row["id"],
                local_reviewer_id,
                *values,
                row["review_status"],
                row["updated_at"],
            ),
        )


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(db_path)) as connection:
        connection.executescript(SCHEMA)
        existing_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(review_items)"
            ).fetchall()
        }
        for column, definition in LEGACY_MIGRATION_COLUMNS.items():
            if column not in existing_columns:
                connection.execute(
                    f"ALTER TABLE review_items ADD COLUMN {column} {definition}"
                )
        item_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(review_items)"
            ).fetchall()
        }
        for column, definition in ITEM_MIGRATION_COLUMNS.items():
            if column not in item_columns:
                connection.execute(
                    f"ALTER TABLE review_items ADD COLUMN {column} {definition}"
                )
        reviewer_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(reviewers)"
            ).fetchall()
        }
        for column, definition in REVIEWER_MIGRATION_COLUMNS.items():
            if column not in reviewer_columns:
                connection.execute(
                    f"ALTER TABLE reviewers ADD COLUMN {column} {definition}"
                )
        failure_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(failure_reviews)"
            ).fetchall()
        }
        for column, definition in FAILURE_MIGRATION_COLUMNS.items():
            if column not in failure_columns:
                connection.execute(
                    f"ALTER TABLE failure_reviews ADD COLUMN {column} {definition}"
                )
        _migrate_reviewers(connection)
        _migrate_legacy_reviews(connection)
        connection.commit()


def get_or_create_reviewer(
    db_path: Path,
    name: str,
) -> tuple[dict[str, object], bool]:
    init_db(db_path)
    display_name = " ".join(name.split())
    normalized_name = normalize_reviewer_name(display_name)
    if not normalized_name:
        raise ValueError("Reviewer name cannot be empty.")
    with closing(connect(db_path)) as connection:
        row = connection.execute(
            """
            SELECT * FROM reviewers
            WHERE normalized_name = ? AND is_active = 1
            """,
            (normalized_name,),
        ).fetchone()
        if row is not None:
            connection.execute(
                "UPDATE reviewers SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (row["id"],),
            )
            connection.commit()
            reviewer = get_reviewer(db_path, int(row["id"]))
            assert reviewer is not None
            return reviewer, False
        cursor = connection.execute(
            """
            INSERT INTO reviewers (name, normalized_name, access_token)
            VALUES (?, ?, NULL)
            """,
            (display_name, normalized_name),
        )
        reviewer_id = int(cursor.lastrowid)
        connection.commit()
    reviewer = get_reviewer(db_path, reviewer_id)
    assert reviewer is not None
    return reviewer, True


def get_or_create_local_reviewer(db_path: Path) -> dict[str, object]:
    init_db(db_path)
    with closing(connect(db_path)) as connection:
        reviewer_id = _ensure_local_reviewer(connection)
        connection.commit()
    reviewer = get_reviewer(db_path, reviewer_id)
    assert reviewer is not None
    return reviewer


def get_reviewer(
    db_path: Path,
    reviewer_id: int,
) -> dict[str, object] | None:
    init_db(db_path)
    with closing(connect(db_path)) as connection:
        row = connection.execute(
            "SELECT * FROM reviewers WHERE id = ? AND is_active = 1",
            (reviewer_id,),
        ).fetchone()
    return dict(row) if row else None


def list_reviewers(db_path: Path) -> list[dict[str, object]]:
    init_db(db_path)
    with closing(connect(db_path)) as connection:
        rows = connection.execute(
            """
            SELECT id, name, is_active, created_at,
                   CASE WHEN access_token IS NULL THEN 0 ELSE 1 END AS has_token
            FROM reviewers ORDER BY id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def import_items(db_path: Path, items: Iterable[dict[str, object]]) -> int:
    init_db(db_path)
    count = 0
    with closing(connect(db_path)) as connection:
        for item in items:
            connection.execute(
                """
                INSERT INTO review_items (
                    item_number, doc_id, page_index, scan_path,
                    audio_path, track_paths
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_number) DO UPDATE SET
                    doc_id = excluded.doc_id,
                    page_index = excluded.page_index,
                    scan_path = excluded.scan_path,
                    audio_path = excluded.audio_path,
                    track_paths = excluded.track_paths
                """,
                (
                    item["item_number"],
                    item["doc_id"],
                    item["page_index"],
                    item["scan_path"],
                    item["audio_path"],
                    json.dumps(item["track_paths"], ensure_ascii=False),
                ),
            )
            count += 1
        connection.commit()
    return count


def _deserialize_item(row: sqlite3.Row | None) -> dict[str, object] | None:
    if row is None:
        return None
    item = dict(row)
    item["track_paths"] = json.loads(str(item["track_paths"]))
    return item


def list_items(
    db_path: Path,
    reviewer_id: int,
    status: str | None = None,
) -> list[dict[str, object]]:
    init_db(db_path)
    query = """
        SELECT i.id, i.item_number, i.doc_id, i.page_index,
               i.scan_path, i.audio_path, i.track_paths, i.review_set,
               COALESCE(r.review_status, 'not_reviewed') AS review_status
        FROM review_items i
        LEFT JOIN reviews r
          ON r.review_item_id = i.id AND r.reviewer_id = ?
    """
    parameters: list[object] = [reviewer_id]
    if status:
        query += " WHERE COALESCE(r.review_status, 'not_reviewed') = ?"
        parameters.append(status)
    query += " ORDER BY i.item_number"
    with closing(connect(db_path)) as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [_deserialize_item(row) for row in rows]  # type: ignore[misc]


def get_item(
    db_path: Path,
    item_number: int,
    reviewer_id: int | None = None,
) -> dict[str, object] | None:
    init_db(db_path)
    if reviewer_id is None:
        query = "SELECT * FROM review_items WHERE item_number = ?"
        parameters = (item_number,)
    else:
        text_fields = {
            "reviewer",
            "review_date",
            "page_usable",
            "dominant_error",
            "expert_comment",
        }
        review_columns = ", ".join(
            f"COALESCE(r.{field}, {repr('') if field in text_fields else 0}) "
            f"AS {field}"
            for field in REVIEW_FIELDS
        )
        query = f"""
            SELECT i.id, i.item_number, i.doc_id, i.page_index,
                   i.scan_path, i.audio_path, i.track_paths, i.review_set,
                   COALESCE(r.review_status, 'not_reviewed') AS review_status,
                   {review_columns},
                   r.updated_at
            FROM review_items i
            LEFT JOIN reviews r
              ON r.review_item_id = i.id AND r.reviewer_id = ?
            WHERE i.item_number = ?
        """
        parameters = (reviewer_id, item_number)
    with closing(connect(db_path)) as connection:
        row = connection.execute(query, parameters).fetchone()
    return _deserialize_item(row)


def get_item_by_page(
    db_path: Path,
    doc_id: str,
    page_index: int,
    reviewer_id: int | None = None,
) -> dict[str, object] | None:
    """Return the review item for a document page, if it is in the review set."""
    init_db(db_path)
    with closing(connect(db_path)) as connection:
        row = connection.execute(
            """
            SELECT item_number
            FROM review_items
            WHERE doc_id = ? AND page_index = ?
            ORDER BY item_number
            LIMIT 1
            """,
            (doc_id, page_index),
        ).fetchone()
    if row is None:
        return None
    return get_item(db_path, int(row["item_number"]), reviewer_id)


def get_review(
    db_path: Path,
    item_number: int,
    reviewer_id: int,
) -> dict[str, object] | None:
    with closing(connect(db_path)) as connection:
        row = connection.execute(
            """
            SELECT r.* FROM reviews r
            JOIN review_items i ON i.id = r.review_item_id
            WHERE i.item_number = ? AND r.reviewer_id = ?
            """,
            (item_number, reviewer_id),
        ).fetchone()
    return dict(row) if row else None


def save_review(
    db_path: Path,
    item_number: int,
    reviewer_id: int,
    values: dict[str, object],
    status: str,
) -> None:
    init_db(db_path)
    fields = ", ".join(REVIEW_FIELDS)
    placeholders = ", ".join("?" for _ in REVIEW_FIELDS)
    updates = ", ".join(f"{field} = excluded.{field}" for field in REVIEW_FIELDS)
    with closing(connect(db_path)) as connection:
        item = connection.execute(
            "SELECT id FROM review_items WHERE item_number = ?",
            (item_number,),
        ).fetchone()
        reviewer = connection.execute(
            "SELECT id FROM reviewers WHERE id = ? AND is_active = 1",
            (reviewer_id,),
        ).fetchone()
        if item is None:
            raise KeyError(f"Unknown review item: {item_number}")
        if reviewer is None:
            raise PermissionError("An active reviewer is required.")
        connection.execute(
            f"""
            INSERT INTO reviews (
                review_item_id, reviewer_id, {fields},
                review_status, updated_at
            ) VALUES (?, ?, {placeholders}, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(review_item_id, reviewer_id) DO UPDATE SET
                {updates},
                review_status = excluded.review_status,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                item["id"],
                reviewer_id,
                *(values[field] for field in REVIEW_FIELDS),
                status,
            ),
        )
        connection.commit()


def list_all_reviews(db_path: Path) -> list[dict[str, object]]:
    init_db(db_path)
    with closing(connect(db_path)) as connection:
        rows = connection.execute(
            """
            SELECT i.doc_id, i.page_index,
                   r.reviewer_id, rv.name AS reviewer_name,
                   r.*
            FROM reviews r
            JOIN review_items i ON i.id = r.review_item_id
            JOIN reviewers rv ON rv.id = r.reviewer_id
            ORDER BY i.item_number, r.reviewer_id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def adjacent_item_numbers(
    db_path: Path,
    item_number: int,
) -> tuple[int | None, int | None]:
    with closing(connect(db_path)) as connection:
        previous_row = connection.execute(
            """
            SELECT item_number FROM review_items
            WHERE item_number < ? ORDER BY item_number DESC LIMIT 1
            """,
            (item_number,),
        ).fetchone()
        next_row = connection.execute(
            """
            SELECT item_number FROM review_items
            WHERE item_number > ? ORDER BY item_number LIMIT 1
            """,
            (item_number,),
        ).fetchone()
    return (
        previous_row["item_number"] if previous_row else None,
        next_row["item_number"] if next_row else None,
    )


def import_failure_items(
    db_path: Path,
    items: Iterable[dict[str, object]],
) -> int:
    """Upsert failed OMR pages without overwriting existing manual reviews."""
    init_db(db_path)
    count = 0
    with closing(connect(db_path)) as connection:
        for item in items:
            connection.execute(
                """
                INSERT INTO failure_reviews (
                    doc_id, page_index, page_type, has_music_manual,
                    cnn_prediction, classical_prediction, sample_group,
                    source_reason, image_path, omr_dir,
                    log_path, failure_status, audiveris_log_excerpt,
                    fallback_400_status, fallback_400_mxl_path,
                    fallback_400_midi_path, fallback_400_runtime_seconds,
                    fallback_400_error, preprocessing_fallback_status,
                    preprocessing_best_variant, preprocessing_mxl_path,
                    preprocessing_midi_path, preprocessing_runtime_seconds,
                    preprocessing_error
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?
                )
                ON CONFLICT(doc_id, page_index) DO UPDATE SET
                    page_type = excluded.page_type,
                    has_music_manual = excluded.has_music_manual,
                    cnn_prediction = excluded.cnn_prediction,
                    classical_prediction = excluded.classical_prediction,
                    sample_group = excluded.sample_group,
                    source_reason = excluded.source_reason,
                    image_path = excluded.image_path,
                    omr_dir = excluded.omr_dir,
                    log_path = excluded.log_path,
                    failure_status = excluded.failure_status,
                    fallback_400_status = CASE
                        WHEN excluded.fallback_400_status = ''
                        THEN failure_reviews.fallback_400_status
                        ELSE excluded.fallback_400_status
                    END,
                    fallback_400_mxl_path = CASE
                        WHEN excluded.fallback_400_status = ''
                        THEN failure_reviews.fallback_400_mxl_path
                        ELSE excluded.fallback_400_mxl_path
                    END,
                    fallback_400_midi_path = CASE
                        WHEN excluded.fallback_400_status = ''
                        THEN failure_reviews.fallback_400_midi_path
                        ELSE excluded.fallback_400_midi_path
                    END,
                    fallback_400_runtime_seconds = CASE
                        WHEN excluded.fallback_400_status = ''
                        THEN failure_reviews.fallback_400_runtime_seconds
                        ELSE excluded.fallback_400_runtime_seconds
                    END,
                    fallback_400_error = CASE
                        WHEN excluded.fallback_400_status = ''
                        THEN failure_reviews.fallback_400_error
                        ELSE excluded.fallback_400_error
                    END,
                    preprocessing_fallback_status = CASE
                        WHEN excluded.preprocessing_fallback_status = ''
                        THEN failure_reviews.preprocessing_fallback_status
                        ELSE excluded.preprocessing_fallback_status
                    END,
                    preprocessing_best_variant = CASE
                        WHEN excluded.preprocessing_fallback_status = ''
                        THEN failure_reviews.preprocessing_best_variant
                        ELSE excluded.preprocessing_best_variant
                    END,
                    preprocessing_mxl_path = CASE
                        WHEN excluded.preprocessing_fallback_status = ''
                        THEN failure_reviews.preprocessing_mxl_path
                        ELSE excluded.preprocessing_mxl_path
                    END,
                    preprocessing_midi_path = CASE
                        WHEN excluded.preprocessing_fallback_status = ''
                        THEN failure_reviews.preprocessing_midi_path
                        ELSE excluded.preprocessing_midi_path
                    END,
                    preprocessing_runtime_seconds = CASE
                        WHEN excluded.preprocessing_fallback_status = ''
                        THEN failure_reviews.preprocessing_runtime_seconds
                        ELSE excluded.preprocessing_runtime_seconds
                    END,
                    preprocessing_error = CASE
                        WHEN excluded.preprocessing_fallback_status = ''
                        THEN failure_reviews.preprocessing_error
                        ELSE excluded.preprocessing_error
                    END,
                    audiveris_log_excerpt = CASE
                        WHEN failure_reviews.audiveris_log_excerpt = ''
                        THEN excluded.audiveris_log_excerpt
                        ELSE failure_reviews.audiveris_log_excerpt
                    END
                """,
                (
                    item["doc_id"],
                    item["page_index"],
                    item.get("page_type", ""),
                    item.get("has_music_manual", ""),
                    item.get("cnn_prediction", ""),
                    item.get("classical_prediction", ""),
                    item.get("sample_group", ""),
                    item.get("source_reason", ""),
                    item["image_path"],
                    item["omr_dir"],
                    item.get("log_path", ""),
                    item.get("failure_status", "missing_mxl"),
                    item.get("audiveris_log_excerpt", ""),
                    item.get("fallback_400_status", ""),
                    item.get("fallback_400_mxl_path", ""),
                    item.get("fallback_400_midi_path", ""),
                    item.get("fallback_400_runtime_seconds"),
                    item.get("fallback_400_error", ""),
                    item.get("preprocessing_fallback_status", ""),
                    item.get("preprocessing_best_variant", ""),
                    item.get("preprocessing_mxl_path", ""),
                    item.get("preprocessing_midi_path", ""),
                    item.get("preprocessing_runtime_seconds"),
                    item.get("preprocessing_error", ""),
                ),
            )
            count += 1
        connection.commit()
    return count


def list_failure_reviews(
    db_path: Path,
    status: str | None = None,
) -> list[dict[str, object]]:
    """List failed pages, optionally filtering by review state."""
    init_db(db_path)
    query = "SELECT * FROM failure_reviews"
    parameters: list[object] = []
    if status == "unknown_failure":
        query += " WHERE failure_reason = 'unknown_failure'"
    elif status in {"draft", "reviewed"}:
        query += " WHERE review_status = ?"
        parameters.append(status)
    elif status == "should_not_send":
        query += " WHERE should_send_to_omr = 'false'"
    elif status == "classifier_false_positive":
        query += """
            WHERE classifier_error_type = 'false_positive_music'
               OR failure_reason = 'classifier_false_positive'
        """
    elif status == "non_music_pages":
        query += """
            WHERE COALESCE(NULLIF(corrected_page_type, ''), page_type)
                  IN ('title', 'cover', 'text', 'blank')
        """
    elif status == "real_omr_failures":
        placeholders = ", ".join("?" for _ in REAL_OMR_FAILURE_REASONS)
        query += (
            f" WHERE failure_reason IN ({placeholders})"
            " AND should_send_to_omr != 'false'"
        )
        parameters.extend(REAL_OMR_FAILURE_REASONS)
    elif status == "still_failed":
        query += """
            WHERE fallback_400_status = 'still_failed'
              AND preprocessing_fallback_status IN (
                  '', 'still_failed', 'preprocessing_failed', 'failed'
              )
        """
    query += " ORDER BY doc_id, page_index"
    with closing(connect(db_path)) as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [dict(row) for row in rows]


def get_failure_review(
    db_path: Path,
    failure_id: int,
) -> dict[str, object] | None:
    init_db(db_path)
    with closing(connect(db_path)) as connection:
        row = connection.execute(
            "SELECT * FROM failure_reviews WHERE id = ?",
            (failure_id,),
        ).fetchone()
    return dict(row) if row else None


def save_failure_review(
    db_path: Path,
    failure_id: int,
    values: dict[str, object],
    reviewer: str,
    status: str,
) -> None:
    """Update one failure classification."""
    init_db(db_path)
    if status not in {"draft", "reviewed"}:
        raise ValueError(f"Unsupported failure review status: {status}")
    with closing(connect(db_path)) as connection:
        cursor = connection.execute(
            """
            UPDATE failure_reviews
            SET failure_reason = ?,
                image_quality_issue = ?,
                decision = ?,
                audiveris_log_excerpt = ?,
                expert_comment = ?,
                corrected_page_type = ?,
                corrected_has_music = ?,
                should_send_to_omr = ?,
                classifier_error_type = ?,
                reviewer = ?,
                review_status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                values["failure_reason"],
                values["image_quality_issue"],
                values["decision"],
                values["audiveris_log_excerpt"],
                values["expert_comment"],
                values["corrected_page_type"],
                values["corrected_has_music"],
                values["should_send_to_omr"],
                values["classifier_error_type"],
                reviewer,
                status,
                failure_id,
            ),
        )
        if cursor.rowcount == 0:
            raise KeyError(f"Unknown failure review: {failure_id}")
        connection.commit()


def adjacent_failure_ids(
    db_path: Path,
    failure_id: int,
) -> tuple[int | None, int | None]:
    with closing(connect(db_path)) as connection:
        current = connection.execute(
            "SELECT doc_id, page_index FROM failure_reviews WHERE id = ?",
            (failure_id,),
        ).fetchone()
        if current is None:
            return None, None
        ordered = connection.execute(
            "SELECT id FROM failure_reviews ORDER BY doc_id, page_index"
        ).fetchall()
    ids = [int(row["id"]) for row in ordered]
    position = ids.index(failure_id)
    return (
        ids[position - 1] if position > 0 else None,
        ids[position + 1] if position + 1 < len(ids) else None,
    )
