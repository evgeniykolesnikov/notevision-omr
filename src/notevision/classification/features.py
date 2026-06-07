"""Feature extraction for rule-based music page classification."""

from pathlib import Path
from typing import Union

import cv2
import numpy as np

PathLike = Union[str, Path]


def _line_centers(horizontal_mask: np.ndarray) -> list[float]:
    """Return vertical centers of contiguous horizontal-line bands."""
    row_has_line = np.count_nonzero(horizontal_mask, axis=1) > 0
    centers: list[float] = []
    start: int | None = None

    for row_index, is_line in enumerate(row_has_line):
        if is_line and start is None:
            start = row_index
        elif not is_line and start is not None:
            centers.append((start + row_index - 1) / 2)
            start = None

    if start is not None:
        centers.append((start + len(row_has_line) - 1) / 2)

    return centers


def _count_staff_like_groups(line_centers: list[float], image_height: int) -> int:
    """Count non-overlapping groups of five approximately equidistant lines."""
    group_count = 0
    index = 0

    while index + 4 < len(line_centers):
        group = line_centers[index : index + 5]
        gaps = np.diff(group)
        mean_gap = float(np.mean(gaps))
        gap_tolerance = max(2.0, mean_gap * 0.35)
        maximum_gap = max(3.0, image_height * 0.05)

        if (
            2.0 <= mean_gap <= maximum_gap
            and float(np.max(np.abs(gaps - mean_gap))) <= gap_tolerance
        ):
            group_count += 1
            index += 5
        else:
            index += 1

    return group_count


def extract_page_features(image_path: PathLike) -> dict[str, object]:
    """Extract baseline visual features from a scanned page image."""
    source = Path(image_path)
    if not source.exists():
        raise FileNotFoundError(f"Page image does not exist: {source}")
    if not source.is_file():
        raise ValueError(f"Page image path is not a file: {source}")

    image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Could not read page image: {source}")

    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(
        grayscale,
        0,
        255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
    )

    image_height, image_width = grayscale.shape
    kernel_width = max(10, image_width // 20)
    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (kernel_width, 1),
    )
    horizontal_mask = cv2.morphologyEx(
        binary,
        cv2.MORPH_OPEN,
        horizontal_kernel,
    )

    line_centers = _line_centers(horizontal_mask)
    pixel_count = image_width * image_height

    return {
        "image_path": str(source),
        "image_width": image_width,
        "image_height": image_height,
        "black_pixel_ratio": float(np.count_nonzero(binary) / pixel_count),
        "horizontal_line_count": len(line_centers),
        "horizontal_line_density": float(
            np.count_nonzero(horizontal_mask) / pixel_count
        ),
        "staff_like_line_groups": _count_staff_like_groups(
            line_centers,
            image_height,
        ),
    }
