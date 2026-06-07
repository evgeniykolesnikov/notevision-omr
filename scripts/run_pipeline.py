"""Detect music pages listed in a PDF page manifest."""

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from notevision.classification.features import extract_page_features
from notevision.classification.predict_pages import rule_based_has_music

OUTPUT_COLUMNS = [
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


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    """Extract features, predict music pages, and save a CSV report."""
    args = parse_args()
    if not args.manifest.is_file():
        raise FileNotFoundError(f"Manifest file does not exist: {args.manifest}")

    manifest = pd.read_csv(args.manifest)
    required_columns = {"doc_id", "page_index", "image_path"}
    missing_columns = required_columns.difference(manifest.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Manifest is missing required columns: {missing}")

    rows: list[dict[str, object]] = []
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

    args.out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=OUTPUT_COLUMNS).to_csv(args.out, index=False)

    print(f"Processed pages: {len(rows)}")
    print(f"Predictions: {args.out}")


if __name__ == "__main__":
    main()
