"""Preprocess labeled music pages for optical music recognition."""

from pathlib import Path
from typing import Union

import cv2
import pandas as pd

PathLike = Union[str, Path]

REPORT_COLUMNS = [
    "doc_id",
    "page_index",
    "input_path",
    "output_path",
    "status",
    "message",
]

REQUIRED_LABEL_COLUMNS = {
    "doc_id",
    "page_index",
    "image_path",
    "has_music",
}


def preprocess_page(image_path: PathLike, output_path: PathLike) -> Path:
    """Convert a page to a contrast-normalized binary grayscale image."""
    source = Path(image_path)
    destination = Path(output_path)
    if not source.is_file():
        raise FileNotFoundError(f"Page image does not exist: {source}")

    grayscale = cv2.imread(str(source), cv2.IMREAD_GRAYSCALE)
    if grayscale is None:
        raise ValueError(f"Could not read page image: {source}")

    contrast_normalizer = cv2.createCLAHE(
        clipLimit=2.0,
        tileGridSize=(8, 8),
    )
    normalized = contrast_normalizer.apply(grayscale)
    _, binary = cv2.threshold(
        normalized,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(destination), binary):
        raise OSError(f"Could not write preprocessed image: {destination}")
    return destination


def preprocess_music_pages(
    labels_df: pd.DataFrame,
    output_dir: PathLike,
    *,
    project_root: PathLike | None = None,
) -> pd.DataFrame:
    """Preprocess every page labeled with ``has_music == 1``."""
    missing = REQUIRED_LABEL_COLUMNS.difference(labels_df.columns)
    if missing:
        missing_names = ", ".join(sorted(missing))
        raise ValueError(f"Labels are missing required columns: {missing_names}")

    invalid_labels = labels_df[
        labels_df["has_music"].isna()
        | ~labels_df["has_music"].isin([0, 1])
    ]
    if not invalid_labels.empty:
        raise ValueError("has_music must contain only 0 or 1")

    destination_root = Path(output_dir)
    root = Path(project_root) if project_root is not None else Path.cwd()
    music_pages = labels_df[labels_df["has_music"] == 1]
    report_rows: list[dict[str, object]] = []

    for page in music_pages.itertuples(index=False):
        source = Path(str(page.image_path))
        if not source.is_absolute():
            source = root / source
        destination = (
            destination_root
            / str(page.doc_id)
            / f"page_{int(page.page_index):03d}_binary.png"
        )

        try:
            preprocess_page(source, destination)
            status = "success"
            message = ""
        except Exception as error:
            status = "error"
            message = str(error)

        report_rows.append(
            {
                "doc_id": page.doc_id,
                "page_index": page.page_index,
                "input_path": str(source),
                "output_path": str(destination),
                "status": status,
                "message": message,
            }
        )

    return pd.DataFrame(report_rows, columns=REPORT_COLUMNS)
