"""Experimental pre-OMR filtering for obvious non-music pages."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

FEATURE_COLUMNS = (
    "dark_pixel_ratio",
    "center_dark_pixel_ratio",
    "horizontal_line_score",
    "staff_line_candidate_count",
    "connected_components_count",
    "estimated_text_density",
    "border_dark_ratio",
)

PREDICTION_COLUMNS = (
    "doc_id",
    "page_index",
    "image_path",
    *FEATURE_COLUMNS,
    "send_to_omr",
    "predicted_non_music_reason",
)


def _page_key(row: dict[str, str]) -> tuple[str, int]:
    doc_id = str(row.get("doc_id", "")).strip()
    try:
        page_index = int(float(str(row.get("page_index", "")).strip()))
    except ValueError as error:
        raise ValueError(f"Invalid page_index for {doc_id or '<missing>'}") from error
    if not doc_id or page_index < 1:
        raise ValueError("Rows require doc_id and positive page_index")
    return doc_id, page_index


def _line_centers(horizontal_mask: np.ndarray) -> list[float]:
    row_has_line = np.count_nonzero(horizontal_mask, axis=1) > 0
    centers: list[float] = []
    start: int | None = None
    for row_index, has_line in enumerate(row_has_line):
        if has_line and start is None:
            start = row_index
        elif not has_line and start is not None:
            centers.append((start + row_index - 1) / 2)
            start = None
    if start is not None:
        centers.append((start + len(row_has_line) - 1) / 2)
    return centers


def extract_pre_omr_features(image_path: str | Path) -> dict[str, float | int]:
    """Extract lightweight page features used before launching Audiveris."""
    source = Path(image_path)
    if not source.is_file():
        raise FileNotFoundError(f"Page image does not exist: {source}")
    image = cv2.imread(str(source), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"Could not read page image: {source}")

    height, width = image.shape
    pixel_count = max(1, height * width)
    dark_mask = image < 210
    dark_pixel_ratio = float(np.count_nonzero(dark_mask) / pixel_count)

    y0, y1 = int(height * 0.2), int(height * 0.8)
    x0, x1 = int(width * 0.2), int(width * 0.8)
    center = dark_mask[y0:y1, x0:x1]
    center_dark_pixel_ratio = float(
        np.count_nonzero(center) / max(1, center.size)
    )

    border = max(1, int(min(height, width) * 0.08))
    border_mask = np.zeros_like(dark_mask, dtype=bool)
    border_mask[:border, :] = True
    border_mask[-border:, :] = True
    border_mask[:, :border] = True
    border_mask[:, -border:] = True
    border_dark_ratio = float(
        np.count_nonzero(dark_mask & border_mask)
        / max(1, np.count_nonzero(border_mask))
    )

    _, binary = cv2.threshold(
        image,
        0,
        255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
    )
    kernel_width = max(12, width // 18)
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
    horizontal_line_score = float(np.count_nonzero(horizontal_mask) / pixel_count)

    components, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    connected_components_count = 0
    text_like_count = 0
    for component_index in range(1, components):
        x, y, component_width, component_height, area = stats[component_index]
        if area < 4 or area > pixel_count * 0.20:
            continue
        connected_components_count += 1
        aspect = component_width / max(1, component_height)
        if (
            4 <= component_height <= max(60, height * 0.08)
            and 2 <= component_width <= max(90, width * 0.15)
            and 0.1 <= aspect <= 12
        ):
            text_like_count += 1

    megapixels = pixel_count / 1_000_000
    estimated_text_density = float(text_like_count / max(0.05, megapixels))

    return {
        "dark_pixel_ratio": dark_pixel_ratio,
        "center_dark_pixel_ratio": center_dark_pixel_ratio,
        "horizontal_line_score": horizontal_line_score,
        "staff_line_candidate_count": len(line_centers),
        "connected_components_count": connected_components_count,
        "estimated_text_density": estimated_text_density,
        "border_dark_ratio": border_dark_ratio,
    }


def classify_pre_omr(features: dict[str, float | int]) -> dict[str, object]:
    """Return a conservative send/skip decision for the pre-OMR stage."""
    dark = float(features["dark_pixel_ratio"])
    center_dark = float(features["center_dark_pixel_ratio"])
    horizontal = float(features["horizontal_line_score"])
    lines = int(features["staff_line_candidate_count"])
    components = int(features["connected_components_count"])
    text_density = float(features["estimated_text_density"])
    border_dark = float(features["border_dark_ratio"])

    reason = "unknown"
    send = True
    if dark < 0.008 and horizontal < 0.0008 and components < 20:
        send = False
        reason = "blank"
    elif border_dark > 0.18 and center_dark < 0.07 and lines < 5:
        send = False
        reason = "cover"
    elif text_density > 450 and lines < 5 and horizontal < 0.004:
        send = False
        reason = "text"
    elif 0.008 <= dark < 0.075 and center_dark < 0.055 and lines < 5:
        send = False
        reason = "title"
    elif 1 <= lines <= 4 and horizontal < 0.006 and text_density < 450:
        send = False
        reason = "decorative"

    return {
        "send_to_omr": send,
        "predicted_non_music_reason": reason,
    }


def resolve_image_path(
    row: dict[str, str],
    *,
    pages_dir: Path,
    project_root: Path,
) -> Path:
    raw_path = str(row.get("image_path", "")).strip()
    if raw_path:
        path = Path(raw_path)
        if not path.is_absolute():
            path = project_root / path
        return path
    doc_id, page_index = _page_key(row)
    return pages_dir / doc_id / f"page_{page_index:03d}.png"


def run_pre_omr_filter(
    candidate_rows: Iterable[dict[str, str]],
    *,
    pages_dir: Path,
    project_root: Path,
) -> list[dict[str, object]]:
    """Score candidates and return one prediction row per input row."""
    predictions: list[dict[str, object]] = []
    seen: set[tuple[str, int]] = set()
    for row in candidate_rows:
        doc_id, page_index = _page_key(row)
        key = (doc_id, page_index)
        if key in seen:
            continue
        seen.add(key)
        image_path = resolve_image_path(
            row,
            pages_dir=pages_dir,
            project_root=project_root,
        )
        features = extract_pre_omr_features(image_path)
        decision = classify_pre_omr(features)
        predictions.append(
            {
                "doc_id": doc_id,
                "page_index": page_index,
                "image_path": image_path.as_posix(),
                **features,
                **decision,
            }
        )
    return predictions


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"CSV file does not exist: {path}")
    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        return list(reader)


def write_predictions_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=PREDICTION_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in PREDICTION_COLUMNS})


def evaluate_against_labels(
    predictions: list[dict[str, object]],
    candidate_rows: Iterable[dict[str, str]],
    failure_review_rows: Iterable[dict[str, str]] = (),
) -> dict[str, object]:
    """Evaluate filter decisions against labels and manual failure review export."""
    prediction_by_key = {
        (str(row["doc_id"]), int(row["page_index"])): row for row in predictions
    }
    candidate_by_key = {
        _page_key(row): row
        for row in candidate_rows
        if row.get("doc_id") and row.get("page_index")
    }

    music_keys = set()
    for key, row in candidate_by_key.items():
        page_type = str(row.get("page_type", "")).strip().lower()
        has_music_value = str(
            row.get("has_music") or row.get("has_music_manual") or ""
        ).strip()
        if page_type in {"music", "mixed"} or has_music_value in {
            "1",
            "true",
            "True",
        }:
            music_keys.add(key)
    wrongly_excluded_music = sorted(
        key
        for key in music_keys
        if key in prediction_by_key
        and not bool(prediction_by_key[key]["send_to_omr"])
    )

    false_positive_keys: set[tuple[str, int]] = set()
    for row in failure_review_rows:
        if not row.get("doc_id") or not row.get("page_index"):
            continue
        classifier_error = str(row.get("classifier_error_type", "")).strip()
        failure_reason = str(row.get("failure_reason", "")).strip()
        corrected_has_music = str(row.get("corrected_has_music", "")).strip()
        should_send = str(row.get("should_send_to_omr", "")).strip()
        if (
            classifier_error == "false_positive_music"
            or failure_reason == "classifier_false_positive"
            or (corrected_has_music == "false" and should_send == "false")
        ):
            false_positive_keys.add(_page_key(row))

    filtered_false_positive_keys = sorted(
        key
        for key in false_positive_keys
        if key in prediction_by_key
        and not bool(prediction_by_key[key]["send_to_omr"])
    )

    reason_counts = Counter(
        str(row["predicted_non_music_reason"])
        for row in predictions
        if not bool(row["send_to_omr"])
    )
    return {
        "total_candidates": len(predictions),
        "send_to_omr": sum(bool(row["send_to_omr"]) for row in predictions),
        "filtered_out": sum(not bool(row["send_to_omr"]) for row in predictions),
        "reason_counts": dict(sorted(reason_counts.items())),
        "false_positive_music_total": len(false_positive_keys),
        "false_positive_music_filtered": len(filtered_false_positive_keys),
        "false_positive_music_filtered_keys": filtered_false_positive_keys,
        "music_mixed_total": len(music_keys),
        "music_mixed_wrongly_filtered": len(wrongly_excluded_music),
        "music_mixed_wrongly_filtered_keys": wrongly_excluded_music,
    }


def format_markdown_report(
    metrics: dict[str, object],
    *,
    candidates_path: Path,
    failure_review_path: Path | None,
    predictions_path: Path,
) -> str:
    reason_counts = metrics["reason_counts"]
    assert isinstance(reason_counts, dict)
    lines = [
        "# Pre-OMR Filter Evaluation",
        "",
        "This is an experimental conservative filter for excluding obvious "
        "blank/title/text/cover/decorative pages before Audiveris. It measures "
        "technical routing decisions only and does not replace manual labels.",
        "",
        "## Inputs",
        "",
        f"- Candidates: `{candidates_path.as_posix()}`",
        f"- Predictions CSV: `{predictions_path.as_posix()}`",
        f"- Failure review export: `{failure_review_path.as_posix() if failure_review_path else 'not provided'}`",
        "",
        "## Summary",
        "",
        f"- Total candidates: {metrics['total_candidates']}",
        f"- Send to OMR: {metrics['send_to_omr']}",
        f"- Filtered out before OMR: {metrics['filtered_out']}",
        "",
        "## Filtered Reasons",
        "",
    ]
    if reason_counts:
        lines.extend(f"- {reason}: {count}" for reason, count in reason_counts.items())
    else:
        lines.append("- none: 0")
    lines.extend(
        [
            "",
            "## Manual Failure Review Check",
            "",
            f"- false_positive_music in failure review: {metrics['false_positive_music_total']}",
            f"- false_positive_music filtered out: {metrics['false_positive_music_filtered']}",
            "",
            "## Safety Check",
            "",
            f"- music/mixed pages in candidates: {metrics['music_mixed_total']}",
            f"- music/mixed pages wrongly filtered out: {metrics['music_mixed_wrongly_filtered']}",
            "",
        ]
    )
    wrong_keys = metrics["music_mixed_wrongly_filtered_keys"]
    if wrong_keys:
        lines.append("### Wrongly Filtered music/mixed Pages")
        lines.append("")
        for doc_id, page_index in wrong_keys:  # type: ignore[assignment]
            lines.append(f"- {doc_id}/page_{page_index:03d}")
        lines.append("")
    return "\n".join(lines)
