"""Train classical or CNN page-classification baselines."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from notevision.page_classifier.classical import (  # noqa: E402
    classification_metrics,
    save_classical_artifact,
    train_classical_models,
)
from notevision.page_classifier.cnn import (  # noqa: E402
    AUGMENTATION_DESCRIPTION,
    filter_readable_records,
    predict_cnn,
    train_cnn,
)
from notevision.page_classifier.dataset import (  # noqa: E402
    MANUAL_SOURCES,
    build_page_records,
    split_by_document,
)

PREDICTION_COLUMNS = [
    "doc_id",
    "page_index",
    "image_path",
    "target",
    "prediction",
    "score",
    "status",
    "error",
]


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _prediction_rows(
    records: list[object],
    predictions: list[object],
    probabilities: list[list[float]],
) -> list[dict[str, object]]:
    rows = []
    for index, (record, prediction) in enumerate(zip(records, predictions)):
        probability = max(probabilities[index]) if probabilities else ""
        rows.append(
            {
                "doc_id": record.doc_id,
                "page_index": record.page_index,
                "image_path": str(record.image_path),
                "target": record.target,
                "prediction": prediction,
                "score": probability,
                "status": "success",
                "error": "",
            }
        )
    return rows


def _write_confusion(path: Path, metrics: dict[str, object]) -> None:
    labels = list(metrics["labels"])
    matrix = metrics["confusion_matrix"]
    rows = [
        {
            "actual": actual,
            **{f"predicted_{predicted}": matrix[actual][predicted] for predicted in labels},
        }
        for actual in labels
    ]
    _write_csv(path, ["actual", *[f"predicted_{label}" for label in labels]], rows)


def _rule_comparison(
    records: list[object],
    ml_f1: float,
    target: str,
) -> str:
    if target != "has_music":
        return (
            "A direct comparison is unavailable because the rule-based detector "
            "predicts only `has_music`, while this run targets `page_type`."
        )
    comparable = [
        record for record in records if record.rule_based_pred is not None
    ]
    if len(comparable) != len(records):
        return (
            "A correct comparison is unavailable because some manual validation "
            "rows do not contain rule-based predictions."
        )
    metrics = classification_metrics(
        [record.has_music for record in comparable],
        [record.rule_based_pred for record in comparable],
    )
    return (
        f"On the same manual document-level validation split: "
        f"ML F1 = {ml_f1:.4f}; rule-based F1 = {float(metrics['f1']):.4f}."
    )


def write_metrics_report(
    path: Path,
    *,
    records_count: int,
    document_count: int,
    train_documents: list[str],
    validation_documents: list[str],
    target: str,
    model: str,
    metrics: dict[str, object],
    epochs: int | str,
    augmentations: str,
    errors_count: int,
    comparison: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    matrix_lines = [
        f"- actual `{actual}`: {values}"
        for actual, values in metrics["confusion_matrix"].items()
    ]
    path.write_text(
        "\n".join(
            [
                "# Page classifier metrics",
                "",
                f"- Pages used: {records_count}",
                f"- Documents: {document_count}",
                f"- Label sources: {', '.join(sorted(MANUAL_SOURCES))}",
                f"- Train documents ({len(train_documents)}): {', '.join(train_documents)}",
                f"- Validation documents ({len(validation_documents)}): {', '.join(validation_documents)}",
                "- Split: document-level; no `doc_id` overlap",
                f"- Target: {target}",
                f"- Model: {model}",
                f"- Epochs: {epochs}",
                f"- Augmentations: {augmentations}",
                f"- Skipped unreadable images: {errors_count}",
                "",
                "## Metrics",
                "",
                f"- Accuracy: {float(metrics['accuracy']):.4f}",
                f"- Precision: {float(metrics['precision']):.4f}",
                f"- Recall: {float(metrics['recall']):.4f}",
                f"- F1: {float(metrics['f1']):.4f}",
                "",
                "## Confusion matrix",
                "",
                *matrix_lines,
                "",
                "## Comparison with rule-based detector",
                "",
                comparison,
                "",
                "## Limitations",
                "",
                "- Evaluation uses only manual labels.",
                "- Pages from one document never appear in both train and validation.",
                "- The corpus is limited and may not represent the full library collection.",
                "- Page-level accuracy does not measure MusicXML musical correctness.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def train(args: argparse.Namespace) -> dict[str, Path]:
    records = build_page_records(
        args.labels,
        args.pages_dir,
        target=args.target,
        manual_only=True,
    )
    train_records, validation_records = split_by_document(
        records,
        validation_fraction=args.validation_fraction,
        random_seed=args.random_seed,
    )
    output_dir = args.out_dir
    metrics_path = output_dir / "page_classifier_metrics.md"
    confusion_path = output_dir / "page_classifier_confusion_matrix.csv"
    predictions_path = output_dir / "page_classifier_predictions.csv"

    if args.model == "classical":
        result = train_classical_models(
            train_records,
            validation_records,
            random_seed=args.random_seed,
        )
        selected = result["selected"]
        valid_records = result["validation_records"]
        prediction_rows = _prediction_rows(
            valid_records,
            selected["predictions"],
            selected["probabilities"],
        )
        prediction_rows.extend(
            {
                **error,
                "target": "",
                "prediction": "",
                "score": "",
                "status": "failed",
            }
            for error in result["errors"]
        )
        model_path = args.model_out or PROJECT_ROOT / "models" / "page_classifier.joblib"
        save_classical_artifact(
            model_path,
            {
                "kind": "classical",
                "target": args.target,
                "model_name": result["selected_name"],
                "model": selected["model"],
                "feature_names": result["feature_names"],
            },
        )
        metrics = selected["metrics"]
        model_name = f"classical/{result['selected_name']}"
        epochs: int | str = "not applicable"
        augmentations = "none"
        errors_count = len(result["errors"])
        comparison_records = valid_records
    else:
        train_available, train_errors = filter_readable_records(train_records)
        val_available, val_errors = filter_readable_records(validation_records)
        model_path = args.model_out or PROJECT_ROOT / "models" / "page_classifier.pt"
        result = train_cnn(
            train_available,
            val_available,
            model_path=model_path,
            target=args.target,
            epochs=args.epochs,
            batch_size=args.batch_size,
            patience=args.patience,
            pretrained=not args.no_pretrained,
        )
        prediction_rows = predict_cnn(model_path, val_available)
        for row, record in zip(prediction_rows, val_available):
            row["target"] = record.target
        prediction_rows.extend(
            {
                **error,
                "target": "",
                "prediction": "",
                "score": "",
                "status": "failed",
            }
            for error in train_errors + val_errors
        )
        metrics = result["metrics"]
        model_name = "cnn/mobilenet_v3_small"
        epochs = f"{result['best_epoch']} best of {args.epochs} requested"
        augmentations = AUGMENTATION_DESCRIPTION
        errors_count = len(train_errors) + len(val_errors)
        comparison_records = val_available

    _write_csv(predictions_path, PREDICTION_COLUMNS, prediction_rows)
    _write_confusion(confusion_path, metrics)
    write_metrics_report(
        metrics_path,
        records_count=len(records),
        document_count=len({record.doc_id for record in records}),
        train_documents=sorted({record.doc_id for record in train_records}),
        validation_documents=sorted({record.doc_id for record in validation_records}),
        target=args.target,
        model=model_name,
        metrics=metrics,
        epochs=epochs,
        augmentations=augmentations,
        errors_count=errors_count,
        comparison=_rule_comparison(
            comparison_records, float(metrics["f1"]), args.target
        ),
    )
    return {
        "metrics": metrics_path,
        "confusion": confusion_path,
        "predictions": predictions_path,
        "model": model_path,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--pages-dir", type=Path, required=True)
    parser.add_argument("--target", choices=("has_music", "page_type"), default="has_music")
    parser.add_argument("--model", choices=("classical", "cnn"), default="classical")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--model-out", type=Path)
    parser.add_argument("--validation-fraction", type=float, default=0.2)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--no-pretrained", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        paths = train(args)
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as error:
        raise SystemExit(f"Error: {error}") from error
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
