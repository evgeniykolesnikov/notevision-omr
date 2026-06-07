"""Evaluate music page detection predictions."""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from notevision.evaluation.metrics import evaluate_binary_predictions


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    """Calculate, print, and save evaluation metrics."""
    args = parse_args()
    if not args.labels.is_file():
        raise FileNotFoundError(f"Labels file does not exist: {args.labels}")
    if not args.predictions.is_file():
        raise FileNotFoundError(
            f"Predictions file does not exist: {args.predictions}"
        )

    labels = pd.read_csv(args.labels)
    predictions = pd.read_csv(args.predictions)
    metrics = evaluate_binary_predictions(labels, predictions)
    output = json.dumps(metrics, ensure_ascii=False, indent=2)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(f"{output}\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
