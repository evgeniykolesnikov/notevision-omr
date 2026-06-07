"""Build a manual page-labeling template from prediction results."""

import argparse
from pathlib import Path

import pandas as pd

OUTPUT_COLUMNS = [
    "doc_id",
    "page_index",
    "page_type",
    "has_music",
    "quality_comment",
    "image_path",
    "has_music_pred",
    "has_music_score",
]

REQUIRED_COLUMNS = {
    "doc_id",
    "page_index",
    "image_path",
    "has_music_pred",
    "has_music_score",
}


def build_labels_template(
    predictions: pd.DataFrame,
    *,
    sample_only: int | None = None,
) -> pd.DataFrame:
    """Create a manual labeling template from page predictions."""
    missing = REQUIRED_COLUMNS.difference(predictions.columns)
    if missing:
        missing_names = ", ".join(sorted(missing))
        raise ValueError(
            f"Predictions are missing required columns: {missing_names}"
        )
    if sample_only is not None and sample_only <= 0:
        raise ValueError(
            f"sample_only must be a positive integer, got: {sample_only}"
        )
    if predictions["has_music_pred"].isna().any() or not predictions[
        "has_music_pred"
    ].isin([0, 1]).all():
        raise ValueError("has_music_pred must contain only 0 or 1")

    selected = predictions.sort_values(
        ["doc_id", "page_index"],
        kind="stable",
    )
    if sample_only is not None:
        selected = selected.groupby("doc_id", sort=False).head(sample_only)

    template = selected[
        [
            "doc_id",
            "page_index",
            "image_path",
            "has_music_pred",
            "has_music_score",
        ]
    ].copy()
    template["has_music_pred"] = template["has_music_pred"].astype(int)
    template["page_type"] = template["has_music_pred"].map(
        {1: "music", 0: "unknown"}
    )
    template["has_music"] = template["has_music_pred"]
    template["quality_comment"] = ""
    return template[OUTPUT_COLUMNS].reset_index(drop=True)


def write_labels_template(
    predictions_path: Path,
    output_path: Path,
    *,
    sample_only: int | None = None,
    overwrite: bool = False,
) -> pd.DataFrame:
    """Read predictions and write a labeling template CSV."""
    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"Output file already exists: {output_path}. "
            "Use --overwrite to replace it."
        )
    if not predictions_path.is_file():
        raise FileNotFoundError(
            f"Predictions file does not exist: {predictions_path}"
        )

    predictions = pd.read_csv(predictions_path)
    template = build_labels_template(
        predictions,
        sample_only=sample_only,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    template.to_csv(output_path, index=False)
    return template


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--sample-only",
        type=int,
        metavar="N",
        help="Use only the first N pages of each document",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output file",
    )
    return parser.parse_args()


def main() -> None:
    """Build and save the labeling template."""
    args = parse_args()
    template = write_labels_template(
        args.predictions,
        args.out,
        sample_only=args.sample_only,
        overwrite=args.overwrite,
    )
    print(f"Template rows: {len(template)}")
    print(f"Labels template: {args.out}")


if __name__ == "__main__":
    main()
