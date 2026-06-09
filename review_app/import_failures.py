"""Import page-level OMR failures into the protected review application."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from review_app.database import DEFAULT_DB_PATH, import_failure_items

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT = PROJECT_ROOT / "outputs" / "reports" / "omr_failure_report.csv"
DEFAULT_LABELS = PROJECT_ROOT / "data" / "labels" / "pages_validated_thesis.csv"
DEFAULT_PAGES_DIR = PROJECT_ROOT / "outputs" / "pages"
DEFAULT_OMR_DIR = PROJECT_ROOT / "outputs" / "omr_300dpi"
DEFAULT_FALLBACK_REPORT = (
    PROJECT_ROOT / "outputs" / "reports" / "omr_400dpi_fallback_report.csv"
)
DEFAULT_PREPROCESSING_REPORT = (
    PROJECT_ROOT
    / "outputs"
    / "reports"
    / "omr_preprocessing_fallback_report.csv"
)


def _page_key(row: dict[str, str]) -> tuple[str, int]:
    doc_id = str(row.get("doc_id", "")).strip()
    try:
        page_index = int(float(str(row.get("page_index", "")).strip()))
    except ValueError as error:
        raise ValueError(
            f"Invalid page_index for {doc_id or '<empty document>'}"
        ) from error
    if not doc_id or page_index < 1:
        raise ValueError("Failure rows require doc_id and positive page_index")
    return doc_id, page_index


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        raise FileNotFoundError(f"CSV file does not exist: {path}")
    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        return list(reader.fieldnames or []), list(reader)


def _relative_to_project(path: Path, project_root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(project_root.resolve()).as_posix()
    except ValueError as error:
        raise ValueError(f"Failure asset must be inside the project: {path}") from error


def _is_failure(row: dict[str, str]) -> bool:
    status = str(
        row.get("failure_type")
        or row.get("failure_status")
        or row.get("status")
        or ""
    ).strip().lower()
    has_mxl = str(row.get("has_mxl", "")).strip().lower()
    return (
        status in {"missing_mxl", "failed", "no_mxl", "no mxl"}
        or has_mxl in {"false", "0", "no"}
    )


def _find_log(page_dir: Path) -> Path | None:
    if not page_dir.is_dir():
        return None
    preferred = sorted(page_dir.glob("*_audiveris.log"))
    if preferred:
        return preferred[-1]
    logs = sorted(page_dir.rglob("*.log"), key=lambda path: path.stat().st_mtime)
    return logs[-1] if logs else None


def _read_log_excerpt(path: Path | None, max_chars: int = 12000) -> str:
    if path is None:
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-max_chars:]


def load_page_types(labels_path: Path | None) -> dict[tuple[str, int], str]:
    if labels_path is None or not labels_path.is_file():
        return {}
    fields, rows = _read_csv(labels_path)
    if not {"doc_id", "page_index", "page_type"}.issubset(fields):
        return {}
    return {_page_key(row): str(row.get("page_type", "")).strip() for row in rows}


def load_fallback_results(
    fallback_report: Path | None,
) -> dict[tuple[str, int], dict[str, object]]:
    if fallback_report is None or not fallback_report.is_file():
        return {}
    fields, rows = _read_csv(fallback_report)
    required = {
        "doc_id",
        "page_index",
        "fallback_400_status",
        "fallback_400_mxl_path",
        "fallback_400_midi_path",
        "fallback_400_runtime_seconds",
        "fallback_400_error",
    }
    if not required.issubset(fields):
        raise ValueError(
            "400 DPI fallback report is missing required columns: "
            + ", ".join(sorted(required - set(fields)))
        )
    results = {}
    for row in rows:
        runtime = str(row.get("fallback_400_runtime_seconds", "")).strip()
        results[_page_key(row)] = {
            "fallback_400_status": row["fallback_400_status"],
            "fallback_400_mxl_path": row["fallback_400_mxl_path"],
            "fallback_400_midi_path": row["fallback_400_midi_path"],
            "fallback_400_runtime_seconds": float(runtime) if runtime else None,
            "fallback_400_error": row["fallback_400_error"],
        }
    return results


def load_preprocessing_results(
    preprocessing_report: Path | None,
) -> dict[tuple[str, int], dict[str, object]]:
    if preprocessing_report is None or not preprocessing_report.is_file():
        return {}
    fields, rows = _read_csv(preprocessing_report)
    required = {
        "doc_id",
        "page_index",
        "variant",
        "preprocessing_fallback_status",
        "preprocessing_mxl_path",
        "preprocessing_midi_path",
        "preprocessing_runtime_seconds",
        "preprocessing_error",
    }
    if not required.issubset(fields):
        raise ValueError(
            "Preprocessing fallback report is missing required columns: "
            + ", ".join(sorted(required - set(fields)))
        )
    grouped: dict[tuple[str, int], list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(_page_key(row), []).append(row)
    results = {}
    for key, page_rows in grouped.items():
        recovered = [
            row
            for row in page_rows
            if row["preprocessing_fallback_status"]
            in {"recovered_mxl", "recovered_midi"}
        ]
        recovered.sort(
            key=lambda row: (
                row["preprocessing_fallback_status"] != "recovered_midi",
                row["variant"],
            )
        )
        best = recovered[0] if recovered else None
        runtime = sum(
            float(row["preprocessing_runtime_seconds"] or 0)
            for row in page_rows
        )
        errors = [
            row["preprocessing_error"].strip()
            for row in page_rows
            if row["preprocessing_error"].strip()
        ]
        results[key] = {
            "preprocessing_fallback_status": (
                best["preprocessing_fallback_status"]
                if best
                else "still_failed"
            ),
            "preprocessing_best_variant": best["variant"] if best else "",
            "preprocessing_mxl_path": (
                best["preprocessing_mxl_path"] if best else ""
            ),
            "preprocessing_midi_path": (
                best["preprocessing_midi_path"] if best else ""
            ),
            "preprocessing_runtime_seconds": runtime,
            "preprocessing_error": " | ".join(dict.fromkeys(errors)),
        }
    return results


def discover_failure_items(
    report_path: Path,
    *,
    project_root: Path = PROJECT_ROOT,
    labels_path: Path | None = DEFAULT_LABELS,
    pages_dir: Path = DEFAULT_PAGES_DIR,
    omr_dir: Path = DEFAULT_OMR_DIR,
    fallback_report: Path | None = DEFAULT_FALLBACK_REPORT,
    preprocessing_report: Path | None = DEFAULT_PREPROCESSING_REPORT,
) -> list[dict[str, object]]:
    """Build import rows from a page-level OMR failure report."""
    fields, rows = _read_csv(report_path)
    if not {"doc_id", "page_index"}.issubset(fields):
        raise ValueError(
            "Failure report must be page-level and contain doc_id,page_index. "
            "Use outputs/reports/omr_failure_report.csv rather than the "
            "document-level omr_pipeline_report.csv."
        )
    page_types = load_page_types(labels_path)
    fallback_results = load_fallback_results(fallback_report)
    preprocessing_results = load_preprocessing_results(preprocessing_report)
    items = []
    for row in rows:
        if not _is_failure(row):
            continue
        doc_id, page_index = _page_key(row)
        raw_image = str(row.get("image_path", "")).strip()
        image_path = (
            (project_root / raw_image).resolve()
            if raw_image
            else (pages_dir / doc_id / f"page_{page_index:03d}.png").resolve()
        )
        page_dir = (omr_dir / doc_id / f"page_{page_index:03d}").resolve()
        log_path = _find_log(page_dir)
        status = str(
            row.get("failure_type")
            or row.get("failure_status")
            or row.get("status")
            or "missing_mxl"
        ).strip()
        items.append(
            {
                "doc_id": doc_id,
                "page_index": page_index,
                "page_type": str(row.get("page_type", "")).strip()
                or page_types.get((doc_id, page_index), ""),
                "image_path": _relative_to_project(image_path, project_root),
                "omr_dir": _relative_to_project(page_dir, project_root),
                "log_path": (
                    _relative_to_project(log_path, project_root)
                    if log_path is not None
                    else ""
                ),
                "failure_status": status or "missing_mxl",
                "audiveris_log_excerpt": _read_log_excerpt(log_path),
                **fallback_results.get((doc_id, page_index), {}),
                **preprocessing_results.get((doc_id, page_index), {}),
            }
        )
    return items


def import_failures(
    report_path: Path,
    db_path: Path,
    **kwargs: object,
) -> int:
    items = discover_failure_items(report_path, **kwargs)
    return import_failure_items(db_path, items)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--pages-dir", type=Path, default=DEFAULT_PAGES_DIR)
    parser.add_argument("--omr-dir", type=Path, default=DEFAULT_OMR_DIR)
    parser.add_argument(
        "--fallback-report",
        type=Path,
        default=DEFAULT_FALLBACK_REPORT,
    )
    parser.add_argument(
        "--preprocessing-report",
        type=Path,
        default=DEFAULT_PREPROCESSING_REPORT,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        count = import_failures(
            args.report,
            args.db,
            project_root=PROJECT_ROOT,
            labels_path=args.labels,
            pages_dir=args.pages_dir,
            omr_dir=args.omr_dir,
            fallback_report=args.fallback_report,
            preprocessing_report=args.preprocessing_report,
        )
    except (FileNotFoundError, ValueError, OSError, csv.Error) as error:
        raise SystemExit(f"Error: {error}") from error
    print(f"Failures imported: {count}")
    print(f"Database: {args.db}")


if __name__ == "__main__":
    main()
