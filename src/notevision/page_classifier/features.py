"""Dependency-light classical image features for scanned pages."""

from __future__ import annotations

import math
from collections import deque
from pathlib import Path

FEATURE_NAMES = (
    "brightness",
    "contrast",
    "black_pixel_ratio",
    "edge_density",
    "horizontal_line_density",
    "staff_like_line_density",
    "connected_component_count",
)


def _load_pgm(path: Path) -> tuple[int, int, list[int]]:
    data = path.read_bytes()
    tokens: list[bytes] = []
    index = 0
    while len(tokens) < 4 and index < len(data):
        while index < len(data) and data[index:index + 1].isspace():
            index += 1
        if index < len(data) and data[index:index + 1] == b"#":
            while index < len(data) and data[index:index + 1] not in b"\r\n":
                index += 1
            continue
        start = index
        while index < len(data) and not data[index:index + 1].isspace():
            index += 1
        tokens.append(data[start:index])
    if len(tokens) != 4 or tokens[0] not in {b"P2", b"P5"}:
        raise ValueError(f"Unsupported PGM file: {path}")
    width, height, maximum = map(int, tokens[1:])
    while index < len(data) and data[index:index + 1].isspace():
        index += 1
    if tokens[0] == b"P5":
        pixels = list(data[index:index + width * height])
    else:
        pixels = [int(value) for value in data[index:].split()]
    if len(pixels) != width * height or maximum <= 0:
        raise ValueError(f"Invalid PGM pixels: {path}")
    if maximum != 255:
        pixels = [round(value * 255 / maximum) for value in pixels]
    return width, height, pixels


def _load_grayscale(path: Path) -> tuple[int, int, list[int]]:
    if path.suffix.lower() == ".pgm":
        return _load_pgm(path)
    try:
        from PIL import Image
    except (ImportError, OSError) as error:
        raise RuntimeError(
            "Reading PNG/JPG pages requires a working Pillow installation."
        ) from error
    try:
        with Image.open(path) as image:
            gray = image.convert("L")
            gray.thumbnail((1000, 1400))
            width, height = gray.size
            return width, height, list(gray.getdata())
    except OSError as error:
        raise ValueError(f"Could not read page image: {path}") from error


def _downsample(
    pixels: list[int],
    width: int,
    height: int,
    maximum_width: int,
    maximum_height: int,
) -> tuple[int, int, list[int]]:
    scale = max(width / maximum_width, height / maximum_height, 1.0)
    target_width = max(1, round(width / scale))
    target_height = max(1, round(height / scale))
    if target_width == width and target_height == height:
        return width, height, pixels
    sampled = [
        pixels[
            min(height - 1, int(y * scale)) * width
            + min(width - 1, int(x * scale))
        ]
        for y in range(target_height)
        for x in range(target_width)
    ]
    return target_width, target_height, sampled


def _staff_groups(line_rows: list[int], height: int) -> int:
    groups = 0
    index = 0
    while index + 4 < len(line_rows):
        rows = line_rows[index : index + 5]
        gaps = [rows[pos + 1] - rows[pos] for pos in range(4)]
        mean_gap = sum(gaps) / 4
        tolerance = max(2.0, mean_gap * 0.35)
        if 2 <= mean_gap <= max(3, height * 0.05) and max(
            abs(gap - mean_gap) for gap in gaps
        ) <= tolerance:
            groups += 1
            index += 5
        else:
            index += 1
    return groups


def _component_count(binary: list[int], width: int, height: int) -> int:
    visited = bytearray(width * height)
    count = 0
    for start, value in enumerate(binary):
        if not value or visited[start]:
            continue
        count += 1
        queue = deque([start])
        visited[start] = 1
        while queue:
            current = queue.popleft()
            x, y = current % width, current // width
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                neighbor = ny * width + nx
                if (
                    0 <= nx < width
                    and 0 <= ny < height
                    and binary[neighbor]
                    and not visited[neighbor]
                ):
                    visited[neighbor] = 1
                    queue.append(neighbor)
    return count


def extract_classical_features(image_path: Path) -> dict[str, float]:
    """Extract normalized features using Pillow only."""
    source = Path(image_path)
    if not source.is_file():
        raise FileNotFoundError(f"Page image does not exist: {source}")
    width, height, pixels = _load_grayscale(source)
    width, height, pixels = _downsample(pixels, width, height, 1000, 1400)
    if width < 2 or height < 2:
        raise ValueError(f"Page image is too small: {source}")

    mean = sum(pixels) / len(pixels)
    brightness = mean / 255.0
    contrast = math.sqrt(
        sum((value - mean) ** 2 for value in pixels) / len(pixels)
    ) / 255.0
    binary = [1 if value < 180 else 0 for value in pixels]
    total = width * height
    black_ratio = sum(binary) / total

    edge_count = 0
    for y in range(height - 1):
        for x in range(width - 1):
            index = y * width + x
            if (
                abs(pixels[index] - pixels[index + 1]) > 35
                or abs(pixels[index] - pixels[index + width]) > 35
            ):
                edge_count += 1
    edge_density = edge_count / total
    line_threshold = max(int(width * 0.45), 1)
    line_rows = [
        row
        for row in range(height)
        if sum(binary[row * width : (row + 1) * width]) >= line_threshold
    ]
    horizontal_line_density = len(line_rows) / height
    staff_like_line_density = _staff_groups(line_rows, height) / max(height / 100.0, 1)

    component_width, component_height, component_pixels = _downsample(
        pixels, width, height, 250, 350
    )
    component_binary = [
        1 if value < 180 else 0 for value in component_pixels
    ]
    component_count = _component_count(
        component_binary, component_width, component_height
    )
    return {
        "brightness": float(brightness),
        "contrast": float(contrast),
        "black_pixel_ratio": float(black_ratio),
        "edge_density": float(edge_density),
        "horizontal_line_density": float(horizontal_line_density),
        "staff_like_line_density": float(staff_like_line_density),
        "connected_component_count": float(math.log1p(component_count)),
    }


def feature_vector(features: dict[str, float]) -> list[float]:
    return [float(features[name]) for name in FEATURE_NAMES]
