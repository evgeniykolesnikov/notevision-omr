"""Evaluate music-page detector predictions against validated labels."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

METRICS_COLUMNS = [
    "tp",
    "fp",
    "tn",
    "fn",
    "accuracy",
    "precision",
    "recall",
    "f1",
]
REQUIRED_COLUMNS = {"has_music", "has_music_pred"}


def _binary(row: dict[str, str], column: str) -> int:
    value = row.get(column, "").strip()
    try:
        parsed = int(float(value))
    except ValueError as error:
        raise ValueError(f"{column} must contain only 0 or 1; got {value!r}") from error
    if parsed not in {0, 1}:
        raise ValueError(f"{column} must contain only 0 or 1; got {value!r}")
    return parsed


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def evaluate_music_detector_rows(
    labels_rows: list[dict[str, str]],
) -> dict[str, int | float]:
    """Calculate confusion matrix values and binary classification metrics."""
    if not labels_rows:
        raise ValueError("Labels CSV contains no rows to evaluate")

    tp = fp = tn = fn = 0
    for row in labels_rows:
        actual = _binary(row, "has_music")
        predicted = _binary(row, "has_music_pred")
        if actual == 1 and predicted == 1:
            tp += 1
        elif actual == 0 and predicted == 1:
            fp += 1
        elif actual == 0 and predicted == 0:
            tn += 1
        else:
            fn += 1

    total = tp + fp + tn + fn
    precision = _safe_ratio(tp, tp + fp)
    recall = _safe_ratio(tp, tp + fn)
    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "accuracy": _safe_ratio(tp + tn, total),
        "precision": precision,
        "recall": recall,
        "f1": _safe_ratio(2 * precision * recall, precision + recall),
    }


def read_labels(path: Path) -> list[dict[str, str]]:
    """Read and validate the columns needed for detector evaluation."""
    if not path.is_file():
        raise FileNotFoundError(f"Labels CSV does not exist: {path}")
    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        missing = sorted(REQUIRED_COLUMNS - set(reader.fieldnames or []))
        if missing:
            raise ValueError(
                "Labels CSV is missing required columns: " + ", ".join(missing)
            )
        return list(reader)


def write_music_detector_metrics(
    labels_path: Path,
    output_path: Path,
) -> dict[str, int | float]:
    """Evaluate labels and save a one-row metrics CSV."""
    metrics = evaluate_music_detector_rows(read_labels(labels_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=METRICS_COLUMNS)
        writer.writeheader()
        writer.writerow(metrics)
    return metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--labels",
        type=Path,
        default=Path("data/labels/pages_validated_thesis.csv"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("outputs/reports/music_detector_metrics.csv"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        metrics = write_music_detector_metrics(args.labels, args.out)
    except (FileNotFoundError, ValueError, OSError, csv.Error) as error:
        raise SystemExit(f"Error: {error}") from error

    print(
        "Confusion matrix: "
        f"TP={metrics['tp']} FP={metrics['fp']} "
        f"TN={metrics['tn']} FN={metrics['fn']}"
    )
    print(
        "Metrics: "
        f"accuracy={metrics['accuracy']:.4f} "
        f"precision={metrics['precision']:.4f} "
        f"recall={metrics['recall']:.4f} "
        f"f1={metrics['f1']:.4f}"
    )
    print(f"Report: {args.out}")


if __name__ == "__main__":
    main()
