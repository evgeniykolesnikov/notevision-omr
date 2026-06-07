"""Run the page extraction and detection pipeline for all raw documents."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

REPORT_COLUMNS = [
    "doc_id",
    "pdf_status",
    "mrc_status",
    "pages_count",
    "predictions_status",
    "error_message",
]

PREDICTION_COLUMNS = [
    "doc_id",
    "page_index",
    "image_path",
    "has_music_pred",
    "has_music_score",
    "black_pixel_ratio",
    "horizontal_line_count",
    "horizontal_line_density",
    "staff_like_line_groups",
]


def find_document_dirs(raw_dir: Path) -> list[Path]:
    """Return document subdirectories in deterministic order."""
    if not raw_dir.is_dir():
        raise FileNotFoundError(f"Raw data directory does not exist: {raw_dir}")
    return sorted(
        (path for path in raw_dir.iterdir() if path.is_dir()),
        key=lambda path: path.name.lower(),
    )


def _predict_manifest(manifest: pd.DataFrame) -> pd.DataFrame:
    from notevision.classification.features import extract_page_features
    from notevision.classification.predict_pages import rule_based_has_music

    rows: list[dict[str, Any]] = []
    for page in manifest.itertuples(index=False):
        features = extract_page_features(page.image_path)
        prediction = rule_based_has_music(features)
        rows.append(
            {
                "doc_id": page.doc_id,
                "page_index": page.page_index,
                "image_path": features["image_path"],
                **prediction,
                "black_pixel_ratio": features["black_pixel_ratio"],
                "horizontal_line_count": features["horizontal_line_count"],
                "horizontal_line_density": features["horizontal_line_density"],
                "staff_like_line_groups": features["staff_like_line_groups"],
            }
        )
    return pd.DataFrame(rows, columns=PREDICTION_COLUMNS)


def _collect_all_predictions(predictions_dir: Path, output_path: Path) -> None:
    prediction_files = sorted(
        predictions_dir.glob("*_page_predictions.csv"),
        key=lambda path: path.name.lower(),
    )
    frames: list[pd.DataFrame] = []
    for prediction_file in prediction_files:
        frame = pd.read_csv(prediction_file)
        frames.append(frame.reindex(columns=PREDICTION_COLUMNS))

    if frames:
        combined = pd.concat(frames, ignore_index=True)
    else:
        combined = pd.DataFrame(columns=PREDICTION_COLUMNS)
    combined.to_csv(output_path, index=False)


def run_batch_pipeline(
    raw_dir: Path,
    outputs_dir: Path,
    dpi: int = 200,
) -> pd.DataFrame:
    """Process every document directory and return the batch report."""
    if dpi <= 0:
        raise ValueError(f"DPI must be a positive integer, got: {dpi}")

    document_dirs = find_document_dirs(raw_dir)
    pages_root = outputs_dir / "pages"
    predictions_root = outputs_dir / "predictions"
    reports_root = outputs_dir / "reports"
    pages_root.mkdir(parents=True, exist_ok=True)
    predictions_root.mkdir(parents=True, exist_ok=True)
    reports_root.mkdir(parents=True, exist_ok=True)

    report_rows: list[dict[str, Any]] = []
    for document_dir in document_dirs:
        doc_id = document_dir.name
        row: dict[str, Any] = {
            "doc_id": doc_id,
            "pdf_status": "pending",
            "mrc_status": "not_processed",
            "pages_count": 0,
            "predictions_status": "not_processed",
            "error_message": "",
        }
        messages: list[str] = []

        try:
            from notevision.pdf.extract_pages import (
                extract_pdf_pages,
                find_pdf_in_document_dir,
            )

            pdf_path = find_pdf_in_document_dir(document_dir)
            page_output_dir = pages_root / doc_id
            manifest = extract_pdf_pages(
                pdf_path,
                page_output_dir,
                doc_id=doc_id,
                dpi=dpi,
            )
            manifest_path = page_output_dir / "manifest.csv"
            manifest.to_csv(manifest_path, index=False)
            row["pdf_status"] = "success"
            row["pages_count"] = len(manifest)
        except Exception as error:
            row["pdf_status"] = "error"
            messages.append(f"PDF: {error}")
            row["error_message"] = " | ".join(messages)
            report_rows.append(row)
            continue

        try:
            from notevision.metadata.parse_mrc import (
                find_mrc_in_document_dir,
                parse_mrc_file,
            )

            mrc_path = find_mrc_in_document_dir(document_dir)
        except FileNotFoundError as warning:
            row["mrc_status"] = "warning"
            messages.append(f"MRC warning: {warning}")
        except Exception as error:
            row["mrc_status"] = "error"
            messages.append(f"MRC: {error}")
        else:
            try:
                metadata = parse_mrc_file(mrc_path, doc_id=doc_id)
                metadata_path = reports_root / f"{doc_id}_metadata.json"
                metadata_path.write_text(
                    json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                row["mrc_status"] = "success"
            except Exception as error:
                row["mrc_status"] = "error"
                messages.append(f"MRC: {error}")

        try:
            predictions = _predict_manifest(manifest)
            predictions_path = (
                predictions_root / f"{doc_id}_page_predictions.csv"
            )
            predictions.to_csv(predictions_path, index=False)
            row["predictions_status"] = "success"
        except Exception as error:
            row["predictions_status"] = "error"
            messages.append(f"Predictions: {error}")

        row["error_message"] = " | ".join(messages)
        report_rows.append(row)

    report = pd.DataFrame(report_rows, columns=REPORT_COLUMNS)
    report_path = reports_root / "batch_pipeline_report.csv"
    report.to_csv(report_path, index=False)
    _collect_all_predictions(
        predictions_root,
        reports_root / "all_page_predictions.csv",
    )
    return report


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--outputs-dir", required=True, type=Path)
    parser.add_argument("--dpi", default=200, type=int)
    return parser.parse_args()


def main() -> None:
    """Run the batch pipeline and print a short summary."""
    args = parse_args()
    report = run_batch_pipeline(args.raw_dir, args.outputs_dir, args.dpi)
    reports_dir = args.outputs_dir / "reports"
    successful = int((report["predictions_status"] == "success").sum())
    errors = int((report["pdf_status"] == "error").sum())
    print(f"Documents processed: {len(report)}")
    print(f"Prediction files created: {successful}")
    print(f"PDF errors: {errors}")
    print(f"Report: {reports_dir / 'batch_pipeline_report.csv'}")
    print(f"All predictions: {reports_dir / 'all_page_predictions.csv'}")


if __name__ == "__main__":
    main()
