"""Export expert reviews from SQLite without modifying the database."""

from __future__ import annotations

import argparse
import csv
import io
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Iterable

from review_app.database import DEFAULT_DB_PATH
from review_app.models import EXPORT_FIELDS


def _normalized_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def _read_only_connection(db_path: Path) -> sqlite3.Connection:
    resolved = db_path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Review database does not exist: {resolved}")
    connection = sqlite3.connect(
        f"file:{resolved.as_posix()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    return connection


def read_export_rows(
    db_path: Path,
    *,
    completed_only: bool = False,
    exclude_reviewers: Iterable[str] = (),
) -> list[dict[str, object]]:
    """Read joined review rows from SQLite using a read-only connection."""
    excluded = {
        _normalized_name(name)
        for name in exclude_reviewers
        if _normalized_name(name)
    }
    query = """
        SELECT
            r.id AS review_id,
            i.item_number,
            i.doc_id,
            i.page_index,
            r.reviewer_id,
            rv.name AS reviewer,
            r.review_status,
            r.review_date,
            r.page_usable,
            r.usability_score,
            r.pitch_problem,
            r.rhythm_problem,
            r.missing_notes_problem,
            r.extra_notes_problem,
            r.chord_problem,
            r.voice_problem,
            r.measure_structure_problem,
            r.playback_problem,
            r.unreadable_or_failed,
            r.dominant_error,
            r.expert_comment,
            r.requires_new_omr,
            r.checked_measures,
            r.correct_measures,
            r.reference_notes,
            r.matched_notes,
            r.pitch_errors,
            r.duration_errors,
            r.missing_notes,
            r.extra_notes,
            r.voice_errors,
            r.measure_errors,
            r.updated_at
        FROM reviews r
        JOIN review_items i ON i.id = r.review_item_id
        JOIN reviewers rv ON rv.id = r.reviewer_id
    """
    parameters: list[object] = []
    if completed_only:
        query += " WHERE r.review_status = ?"
        parameters.append("completed")
    query += " ORDER BY i.item_number, r.reviewer_id"

    try:
        with closing(_read_only_connection(db_path)) as connection:
            rows = connection.execute(query, parameters).fetchall()
    except sqlite3.OperationalError as error:
        raise ValueError(
            f"Review database has no compatible review schema: {db_path}"
        ) from error

    return [
        {field: row[field] for field in EXPORT_FIELDS}
        for row in rows
        if _normalized_name(str(row["reviewer"])) not in excluded
    ]


def build_export_csv(
    db_path: Path,
    *,
    completed_only: bool = False,
    exclude_reviewers: Iterable[str] = (),
) -> str:
    """Return the selected reviews as CSV text."""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_FIELDS)
    writer.writeheader()
    writer.writerows(
        read_export_rows(
            db_path,
            completed_only=completed_only,
            exclude_reviewers=exclude_reviewers,
        )
    )
    return buffer.getvalue()


def export_reviews(
    db_path: Path,
    output_path: Path,
    *,
    completed_only: bool = False,
    exclude_reviewers: Iterable[str] = (),
) -> int:
    """Write a UTF-8 BOM CSV and return the number of exported reviews."""
    rows = read_export_rows(
        db_path,
        completed_only=completed_only,
        exclude_reviewers=exclude_reviewers,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=EXPORT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="SQLite review database (default: review_app/review_app.db).",
    )
    parser.add_argument("--out", required=True, type=Path, help="Output CSV path.")
    parser.add_argument(
        "--completed-only",
        action="store_true",
        help="Export only completed reviews.",
    )
    parser.add_argument(
        "--exclude-reviewer",
        action="append",
        default=[],
        help="Reviewer name to exclude; repeat the option for multiple names.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        count = export_reviews(
            args.db,
            args.out,
            completed_only=args.completed_only,
            exclude_reviewers=args.exclude_reviewer,
        )
    except (FileNotFoundError, ValueError, OSError, sqlite3.Error) as error:
        raise SystemExit(f"Error: {error}") from error
    print(f"Exported reviews: {count}")
    print(f"CSV: {args.out}")


if __name__ == "__main__":
    main()
