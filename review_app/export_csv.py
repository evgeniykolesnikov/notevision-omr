"""CSV export compatible with the thesis expert-evaluation table."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from review_app.database import list_all_reviews
from review_app.models import EXPORT_FIELDS


def build_export_csv(db_path: Path) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_FIELDS)
    writer.writeheader()
    for review in list_all_reviews(db_path):
        row = {field: review.get(field, "") for field in EXPORT_FIELDS}
        row["reviewer"] = review["reviewer_name"]
        writer.writerow(row)
    return buffer.getvalue()
