"""CSV export for failed OMR page classifications."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from review_app.database import list_failure_reviews
from review_app.models import FAILURE_EXPORT_FIELDS


def build_failure_export_csv(db_path: Path) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FAILURE_EXPORT_FIELDS)
    writer.writeheader()
    for failure in list_failure_reviews(db_path):
        row = {field: failure.get(field, "") for field in FAILURE_EXPORT_FIELDS}
        row["original_page_type"] = failure.get("page_type", "")
        writer.writerow(row)
    return buffer.getvalue()
