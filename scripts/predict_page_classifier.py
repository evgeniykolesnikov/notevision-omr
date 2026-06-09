"""Apply a trained page classifier to recursively discovered page PNGs."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from notevision.page_classifier.classical import (  # noqa: E402
    load_classical_artifact,
)
from notevision.page_classifier.cnn import predict_cnn  # noqa: E402
from notevision.page_classifier.dataset import PageRecord  # noqa: E402
from notevision.page_classifier.features import (  # noqa: E402
    extract_classical_features,
    feature_vector,
)

PREDICTION_COLUMNS = [
    "doc_id",
    "page_index",
    "image_path",
    "prediction",
    "score",
    "status",
    "error",
]


def discover_pages(pages_dir: Path) -> list[PageRecord]:
    if not pages_dir.is_dir():
        raise FileNotFoundError(f"Pages directory does not exist: {pages_dir}")
    records = []
    paths = [
        path
        for path in pages_dir.rglob("page_*")
        if path.is_file()
        and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".pgm"}
    ]
    for path in sorted(paths):
        match = re.search(r"page_(\d+)", path.stem, re.IGNORECASE)
        if match is None:
            continue
        doc_id = next(
            (
                part
                for part in reversed(path.parts)
                if re.fullmatch(r"rsl\d+", part, re.IGNORECASE)
            ),
            path.parent.name,
        )
        records.append(
            PageRecord(
                doc_id=doc_id,
                page_index=int(match.group(1)),
                image_path=path.resolve(),
                target=0,
                page_type="unknown",
                has_music=0,
                validation_source="prediction",
            )
        )
    return records


def predict_classical(
    artifact_path: Path,
    records: list[PageRecord],
) -> list[dict[str, object]]:
    artifact = load_classical_artifact(artifact_path)
    model = artifact["model"]
    rows = []
    for record in records:
        try:
            vector = [feature_vector(extract_classical_features(record.image_path))]
            prediction = model.predict(vector)[0]
            score = ""
            if hasattr(model, "predict_proba"):
                score = max(model.predict_proba(vector)[0])
            rows.append(
                {
                    "doc_id": record.doc_id,
                    "page_index": record.page_index,
                    "image_path": str(record.image_path),
                    "prediction": prediction,
                    "score": score,
                    "status": "success",
                    "error": "",
                }
            )
        except Exception as error:
            rows.append(
                {
                    "doc_id": record.doc_id,
                    "page_index": record.page_index,
                    "image_path": str(record.image_path),
                    "prediction": "",
                    "score": "",
                    "status": "failed",
                    "error": str(error),
                }
            )
    return rows


def write_predictions(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=PREDICTION_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--pages-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        records = discover_pages(args.pages_dir)
        rows = (
            predict_cnn(args.model, records)
            if args.model.suffix.lower() == ".pt"
            else predict_classical(args.model, records)
        )
        write_predictions(args.out, rows)
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as error:
        raise SystemExit(f"Error: {error}") from error
    print(f"Pages found: {len(records)}")
    print(f"Successful: {sum(row['status'] == 'success' for row in rows)}")
    print(f"Failed: {sum(row['status'] == 'failed' for row in rows)}")
    print(f"Predictions: {args.out}")


if __name__ == "__main__":
    main()
