"""Evaluation metrics for music page detection."""

from typing import Any

import pandas as pd

KEY_COLUMNS = ["doc_id", "page_index"]


def _require_columns(
    dataframe: pd.DataFrame,
    required: set[str],
    dataframe_name: str,
) -> None:
    missing = required.difference(dataframe.columns)
    if missing:
        missing_names = ", ".join(sorted(missing))
        raise ValueError(
            f"{dataframe_name} is missing required columns: {missing_names}"
        )


def _validate_unique_pages(
    dataframe: pd.DataFrame,
    dataframe_name: str,
) -> None:
    duplicated = dataframe.duplicated(KEY_COLUMNS, keep=False)
    if duplicated.any():
        duplicate_pages = dataframe.loc[duplicated, KEY_COLUMNS].drop_duplicates()
        page_list = ", ".join(
            f"{row.doc_id}/page_{int(row.page_index)}"
            for row in duplicate_pages.itertuples(index=False)
        )
        raise ValueError(
            f"{dataframe_name} contains duplicate page keys: {page_list}"
        )


def _validate_binary_values(series: pd.Series, column_name: str) -> None:
    if series.isna().any() or not series.isin([0, 1]).all():
        invalid = series[series.isna() | ~series.isin([0, 1])].unique().tolist()
        raise ValueError(
            f"{column_name} must contain only 0 or 1; invalid values: {invalid}"
        )


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def _page_type_error_analysis(merged: pd.DataFrame) -> dict[str, dict[str, Any]]:
    analysis: dict[str, dict[str, Any]] = {}
    page_types = merged["page_type"].fillna("<missing>").astype(str)

    for page_type, group in merged.assign(page_type=page_types).groupby(
        "page_type",
        sort=True,
    ):
        actual = group["has_music"].astype(int)
        predicted = group["has_music_pred"].astype(int)
        errors = int((actual != predicted).sum())
        total = int(len(group))
        analysis[str(page_type)] = {
            "total": total,
            "errors": errors,
            "fp": int(((actual == 0) & (predicted == 1)).sum()),
            "fn": int(((actual == 1) & (predicted == 0)).sum()),
            "error_rate": _safe_ratio(errors, total),
        }

    return analysis


def evaluate_binary_predictions(
    labels_df: pd.DataFrame,
    predictions_df: pd.DataFrame,
) -> dict[str, Any]:
    """Evaluate binary predictions matched by ``doc_id`` and ``page_index``."""
    _require_columns(
        labels_df,
        {"doc_id", "page_index", "has_music"},
        "labels_df",
    )
    _require_columns(
        predictions_df,
        {"doc_id", "page_index", "has_music_pred"},
        "predictions_df",
    )
    if labels_df.empty:
        raise ValueError("labels_df contains no pages to evaluate")

    _validate_unique_pages(labels_df, "labels_df")
    _validate_unique_pages(predictions_df, "predictions_df")

    merged = labels_df.merge(
        predictions_df[KEY_COLUMNS + ["has_music_pred"]],
        on=KEY_COLUMNS,
        how="left",
        validate="one_to_one",
        indicator=True,
    )

    missing_rows = merged["_merge"] == "left_only"
    if missing_rows.any():
        missing_pages = merged.loc[missing_rows, KEY_COLUMNS]
        page_list = ", ".join(
            f"{row.doc_id}/page_{int(row.page_index)}"
            for row in missing_pages.itertuples(index=False)
        )
        raise ValueError(
            "Predictions are missing pages present in labels: "
            f"{page_list}"
        )

    _validate_binary_values(merged["has_music"], "labels_df.has_music")
    _validate_binary_values(
        merged["has_music_pred"],
        "predictions_df.has_music_pred",
    )

    actual = merged["has_music"].astype(int)
    predicted = merged["has_music_pred"].astype(int)

    tn = int(((actual == 0) & (predicted == 0)).sum())
    fp = int(((actual == 0) & (predicted == 1)).sum())
    fn = int(((actual == 1) & (predicted == 0)).sum())
    tp = int(((actual == 1) & (predicted == 1)).sum())
    total = tn + fp + fn + tp

    precision = _safe_ratio(tp, tp + fp)
    recall = _safe_ratio(tp, tp + fn)
    result: dict[str, Any] = {
        "accuracy": _safe_ratio(tp + tn, total),
        "precision": precision,
        "recall": recall,
        "f1": _safe_ratio(2 * precision * recall, precision + recall),
        "confusion_matrix": {
            "tn": tn,
            "fp": fp,
            "fn": fn,
            "tp": tp,
        },
    }

    if "page_type" in labels_df.columns:
        result["error_analysis_by_page_type"] = _page_type_error_analysis(
            merged
        )

    return result
