"""Show per-reviewer progress without modifying the review database."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from review_app.database import DEFAULT_DB_PATH


def _normalized_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def collect_review_progress(
    db_path: Path,
    *,
    total: int = 30,
    exclude_reviewers: Iterable[str] = (),
) -> list[dict[str, object]]:
    if total < 1:
        raise ValueError("total must be at least 1")
    resolved = db_path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Review database does not exist: {resolved}")
    excluded = {
        _normalized_name(name)
        for name in exclude_reviewers
        if _normalized_name(name)
    }
    connection = sqlite3.connect(
        f"file:{resolved.as_posix()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT
                rv.name AS reviewer,
                SUM(CASE WHEN r.review_status = 'completed' THEN 1 ELSE 0 END)
                    AS completed,
                SUM(CASE WHEN r.review_status = 'draft' THEN 1 ELSE 0 END)
                    AS draft,
                MAX(r.updated_at) AS last_update
            FROM reviewers rv
            LEFT JOIN reviews r ON r.reviewer_id = rv.id
            WHERE rv.is_active = 1
            GROUP BY rv.id, rv.name
            ORDER BY rv.name COLLATE NOCASE
            """
        ).fetchall()
    except sqlite3.OperationalError as error:
        raise ValueError(
            f"Review database has no compatible review schema: {db_path}"
        ) from error
    finally:
        connection.close()

    result = []
    for row in rows:
        reviewer = str(row["reviewer"])
        if _normalized_name(reviewer) in excluded:
            continue
        completed = int(row["completed"] or 0)
        draft = int(row["draft"] or 0)
        filled = completed + draft
        result.append(
            {
                "reviewer": reviewer,
                "completed": completed,
                "draft": draft,
                "filled": filled,
                "progress": filled / total,
                "last_update": row["last_update"] or "",
            }
        )
    return result


def build_markdown(rows: list[dict[str, object]], total: int) -> str:
    lines = [
        "# Expert review progress",
        "",
        f"Expected items per reviewer: **{total}**.",
        "",
        "| Reviewer | Completed | Draft | Filled | Progress | Last update |",
        "|---|---:|---:|---:|---:|---|",
    ]
    lines.extend(
        "| {reviewer} | {completed} | {draft} | {filled} | "
        "{progress:.1%} | {last_update} |".format(**row)
        for row in rows
    )
    if not rows:
        lines.append("| No active reviewers | 0 | 0 | 0 | 0.0% | |")
    return "\n".join(lines) + "\n"


def print_progress(rows: list[dict[str, object]]) -> None:
    print("reviewer | completed | draft | filled | progress | last_update")
    for row in rows:
        print(
            f"{row['reviewer']} | {row['completed']} | {row['draft']} | "
            f"{row['filled']} | {row['progress']:.1%} | {row['last_update']}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--total", type=int, default=30)
    parser.add_argument(
        "--exclude-reviewer",
        action="append",
        default=[],
        help="Reviewer name to exclude; may be repeated.",
    )
    parser.add_argument("--markdown-out", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        rows = collect_review_progress(
            args.db,
            total=args.total,
            exclude_reviewers=args.exclude_reviewer,
        )
    except (FileNotFoundError, ValueError, OSError, sqlite3.Error) as error:
        raise SystemExit(f"Error: {error}") from error
    print_progress(rows)
    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(
            build_markdown(rows, args.total),
            encoding="utf-8",
        )
        print(f"Markdown: {args.markdown_out}")


if __name__ == "__main__":
    main()
