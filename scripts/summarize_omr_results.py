"""Summarize Audiveris OMR report rows and generated MusicXML archives."""

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

REQUIRED_REPORT_COLUMNS = {
    "doc_id",
    "page_index",
    "status",
    "message",
}


def _find_page_mxl(
    row: Any,
    omr_dir: Path,
    project_root: Path,
) -> Path | None:
    output_dir_value = getattr(row, "output_dir", "")
    if output_dir_value:
        output_dir = Path(str(output_dir_value))
        if not output_dir.is_absolute():
            output_dir = project_root / output_dir
        matches = sorted(output_dir.rglob("*.mxl"))
        if matches:
            return matches[0]

    fallback_dir = (
        omr_dir
        / str(row.doc_id)
        / f"page_{int(row.page_index):03d}"
    )
    matches = sorted(fallback_dir.rglob("*.mxl"))
    return matches[0] if matches else None


def summarize_omr_results(
    omr_report: pd.DataFrame,
    omr_dir: Path,
    *,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Build aggregate metrics and page-level lists for OMR results."""
    missing = REQUIRED_REPORT_COLUMNS.difference(omr_report.columns)
    if missing:
        missing_names = ", ".join(sorted(missing))
        raise ValueError(
            f"OMR report is missing required columns: {missing_names}"
        )

    root = project_root or Path.cwd()
    resolved_omr_dir = omr_dir if omr_dir.is_absolute() else root / omr_dir
    mxl_files = sorted(resolved_omr_dir.rglob("*.mxl"))
    mxl_sizes = [path.stat().st_size for path in mxl_files]

    statuses = omr_report["status"].astype(str).str.lower()
    success_count = int((statuses == "success").sum())
    failed_count = int((statuses == "failed").sum())
    total = int(len(omr_report))

    successful_pages: list[dict[str, Any]] = []
    failed_pages: list[dict[str, Any]] = []
    for row in omr_report.itertuples(index=False):
        status = str(row.status).lower()
        if status == "success":
            mxl_path = _find_page_mxl(row, resolved_omr_dir, root)
            successful_pages.append(
                {
                    "doc_id": row.doc_id,
                    "page_index": int(row.page_index),
                    "mxl_path": str(mxl_path) if mxl_path else None,
                    "mxl_size": mxl_path.stat().st_size if mxl_path else None,
                }
            )
        elif status == "failed":
            failed_pages.append(
                {
                    "doc_id": row.doc_id,
                    "page_index": int(row.page_index),
                    "message": str(row.message),
                }
            )

    return {
        "total": total,
        "success": success_count,
        "failed": failed_count,
        "success_rate": float(success_count / total) if total else 0.0,
        "mxl_count": len(mxl_files),
        "mxl_size": {
            "min": min(mxl_sizes) if mxl_sizes else None,
            "max": max(mxl_sizes) if mxl_sizes else None,
            "mean": (
                float(sum(mxl_sizes) / len(mxl_sizes))
                if mxl_sizes
                else None
            ),
        },
        "successful_pages": successful_pages,
        "failed_pages": failed_pages,
    }


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--omr-report", required=True, type=Path)
    parser.add_argument("--omr-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    """Create, save, and print the OMR summary."""
    args = parse_args()
    if not args.omr_report.is_file():
        raise FileNotFoundError(
            f"OMR report file does not exist: {args.omr_report}"
        )
    if not args.omr_dir.is_dir():
        raise FileNotFoundError(
            f"OMR output directory does not exist: {args.omr_dir}"
        )

    report = pd.read_csv(args.omr_report, keep_default_na=False)
    summary = summarize_omr_results(report, args.omr_dir)
    output = json.dumps(summary, ensure_ascii=False, indent=2)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(f"{output}\n", encoding="utf-8")

    print(f"Total pages: {summary['total']}")
    print(f"Successful: {summary['success']}")
    print(f"Failed: {summary['failed']}")
    print(f"Success rate: {summary['success_rate']:.4f}")
    print(f"MXL files: {summary['mxl_count']}")
    print(f"Summary: {args.out}")


if __name__ == "__main__":
    main()
