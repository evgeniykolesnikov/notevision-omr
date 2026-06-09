"""Scikit-learn baselines and dependency-light evaluation helpers."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .dataset import PageRecord
from .features import FEATURE_NAMES, extract_classical_features, feature_vector


def classification_metrics(
    truth: list[int | str],
    predictions: list[int | str],
) -> dict[str, object]:
    labels = sorted(set(truth) | set(predictions), key=str)
    matrix = {
        str(actual): {
            str(predicted): int(sum(
                a == actual and p == predicted
                for a, p in zip(truth, predictions)
            ))
            for predicted in labels
        }
        for actual in labels
    }
    total = len(truth)
    accuracy = sum(a == p for a, p in zip(truth, predictions)) / total if total else 0.0
    if set(labels).issubset({0, 1}) and 1 in labels:
        tp = sum(a == 1 and p == 1 for a, p in zip(truth, predictions))
        fp = sum(a != 1 and p == 1 for a, p in zip(truth, predictions))
        fn = sum(a == 1 and p != 1 for a, p in zip(truth, predictions))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return {
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "labels": [str(label) for label in labels],
            "confusion_matrix": matrix,
        }
    per_label = []
    for label in labels:
        tp = sum(a == label and p == label for a, p in zip(truth, predictions))
        fp = sum(a != label and p == label for a, p in zip(truth, predictions))
        fn = sum(a == label and p != label for a, p in zip(truth, predictions))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_label.append((precision, recall, f1))
    return {
        "accuracy": accuracy,
        "precision": sum(value[0] for value in per_label) / len(per_label) if per_label else 0.0,
        "recall": sum(value[1] for value in per_label) / len(per_label) if per_label else 0.0,
        "f1": sum(value[2] for value in per_label) / len(per_label) if per_label else 0.0,
        "labels": [str(label) for label in labels],
        "confusion_matrix": matrix,
    }


def extract_record_features(
    records: list[PageRecord],
) -> tuple[list[PageRecord], list[list[float]], list[dict[str, str]]]:
    valid, vectors, errors = [], [], []
    for record in records:
        try:
            features = extract_classical_features(record.image_path)
        except (FileNotFoundError, ValueError, OSError) as error:
            errors.append(
                {
                    "doc_id": record.doc_id,
                    "page_index": str(record.page_index),
                    "image_path": str(record.image_path),
                    "error": str(error),
                }
            )
            continue
        valid.append(record)
        vectors.append(feature_vector(features))
    return valid, vectors, errors


def build_estimators(random_seed: int = 42) -> dict[str, Any]:
    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except (ImportError, OSError) as error:
        raise RuntimeError(
            "Classical training requires a working scikit-learn installation."
        ) from error
    return {
        "logistic_regression": make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=1000, class_weight="balanced", random_state=random_seed),
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=200,
            class_weight="balanced",
            random_state=random_seed,
            n_jobs=-1,
        ),
    }


def train_classical_models(
    train_records: list[PageRecord],
    validation_records: list[PageRecord],
    *,
    random_seed: int = 42,
    estimators: dict[str, Any] | None = None,
) -> dict[str, object]:
    train_valid, train_x, train_errors = extract_record_features(train_records)
    val_valid, val_x, val_errors = extract_record_features(validation_records)
    if not train_valid or not val_valid:
        raise ValueError("Train and validation must contain readable images")
    train_y = [record.target for record in train_valid]
    val_y = [record.target for record in val_valid]
    if len(set(train_y)) < 2:
        raise ValueError("Training split must contain at least two target classes")
    candidates = estimators or build_estimators(random_seed)
    results = {}
    for name, estimator in candidates.items():
        estimator.fit(train_x, train_y)
        predictions = list(estimator.predict(val_x))
        probabilities = []
        if hasattr(estimator, "predict_proba"):
            raw_probabilities = estimator.predict_proba(val_x)
            probabilities = (
                raw_probabilities.tolist()
                if hasattr(raw_probabilities, "tolist")
                else list(raw_probabilities)
            )
        results[name] = {
            "model": estimator,
            "predictions": predictions,
            "probabilities": probabilities,
            "metrics": classification_metrics(val_y, predictions),
        }
    selected_name = max(results, key=lambda name: float(results[name]["metrics"]["f1"]))
    return {
        "selected_name": selected_name,
        "selected": results[selected_name],
        "models": results,
        "train_records": train_valid,
        "validation_records": val_valid,
        "errors": train_errors + val_errors,
        "feature_names": list(FEATURE_NAMES),
    }


def save_classical_artifact(path: Path, payload: dict[str, object]) -> None:
    import joblib

    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(payload, path)


def load_classical_artifact(path: Path) -> dict[str, object]:
    import joblib

    return joblib.load(path)
