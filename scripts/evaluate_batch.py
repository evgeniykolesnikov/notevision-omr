"""Evaluate page predictions collected from multiple documents."""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from notevision.evaluation.metrics import evaluate_batch_predictions

PREDICTION_COLUMNS = ["doc_id", "page_index", "has_music_pred"]


def load_prediction_files(predictions_dir: Path) -> pd.DataFrame:
    """Load and combine all document prediction CSV files."""
    if not predictions_dir.is_dir():
        raise FileNotFoundError(
            f"Predictions directory does not exist: {predictions_dir}"
        )

    prediction_files = sorted(
        predictions_dir.glob("*_page_predictions.csv"),
        key=lambda path: path.name.lower(),
    )
    if not prediction_files:
        return pd.DataFrame(columns=PREDICTION_COLUMNS)

    return pd.concat(
        (pd.read_csv(path) for path in prediction_files),
        ignore_index=True,
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--predictions-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    """Calculate, print, and save batch evaluation metrics."""
    args = parse_args()
    if not args.labels.is_file():
        raise FileNotFoundError(f"Labels file does not exist: {args.labels}")

    labels = pd.read_csv(args.labels)
    predictions = load_prediction_files(args.predictions_dir)
    metrics = evaluate_batch_predictions(labels, predictions)
    output = json.dumps(metrics, ensure_ascii=False, indent=2)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(f"{output}\n", encoding="utf-8")

    confusion = metrics["confusion_matrix"]
    print(f"Documents evaluated: {len(metrics['metrics_by_doc_id'])}")
    print(f"Accuracy: {metrics['accuracy']:.4f}")
    print(f"Precision: {metrics['precision']:.4f}")
    print(f"Recall: {metrics['recall']:.4f}")
    print(f"F1: {metrics['f1']:.4f}")
    print(
        "Confusion matrix: "
        f"tn={confusion['tn']}, fp={confusion['fp']}, "
        f"fn={confusion['fn']}, tp={confusion['tp']}"
    )
    print(f"Metrics: {args.out}")


if __name__ == "__main__":
    main()
