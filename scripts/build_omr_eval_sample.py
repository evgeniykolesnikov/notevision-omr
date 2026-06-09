"""Build a reproducible expanded sample for thesis OMR evaluation."""

from __future__ import annotations

import argparse
import csv
import random
from collections import Counter
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_COLUMNS = [
    "doc_id",
    "page_index",
    "image_path",
    "page_type",
    "has_music_manual",
    "cnn_prediction",
    "classical_prediction",
    "sample_group",
    "source_reason",
]

ELIGIBLE_PAGE_TYPES = {"music", "mixed"}
PREDICTION_COLUMNS = ("prediction", "has_music_pred", "cnn_prediction")
FAILURE_VALUES = {"failed", "missing_mxl", "no mxl", "no_mxl", "still_failed"}
RECOVERED_VALUES = {
    "recovered",
    "success",
    "mxl_generated",
    "midi_generated",
}

GROUP_PRIORITY = {
    "previous_omr_failure": 0,
    "fallback_recovered": 1,
    "model_disagreement": 2,
    "mixed_page": 3,
    "low_confidence_candidate": 4,
    "random_music": 5,
}


def _key(row: dict[str, str]) -> tuple[str, int]:
    doc_id = str(row.get("doc_id", "")).strip()
    try:
        page_index = int(float(str(row.get("page_index", "")).strip()))
    except ValueError as error:
        raise ValueError(
            f"Invalid page_index for {doc_id or '<empty>'}: "
            f"{row.get('page_index', '')!r}"
        ) from error
    if not doc_id or page_index < 1:
        raise ValueError("Rows must contain doc_id and positive page_index")
    return doc_id, page_index


def _optional_binary(value: object) -> int | None:
    text = str(value if value is not None else "").strip().lower()
    if not text or text in {"nan", "none"}:
        return None
    if text in {"true", "yes"}:
        return 1
    if text in {"false", "no"}:
        return 0
    try:
        result = int(float(text))
    except ValueError:
        return None
    return result if result in {0, 1} else None


def _optional_float(value: object) -> float | None:
    text = str(value if value is not None else "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _read_csv(path: Path | None, *, required: bool = False) -> list[dict[str, str]]:
    if path is None or not path.is_file():
        if required:
            raise FileNotFoundError(f"CSV does not exist: {path}")
        return []
    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        columns = set(reader.fieldnames or [])
        missing = {"doc_id", "page_index"} - columns
        if missing:
            raise ValueError(
                f"CSV {path} is missing columns: {', '.join(sorted(missing))}"
            )
        return list(reader)


def _prediction_map(
    rows: Iterable[dict[str, str]],
) -> dict[tuple[str, int], tuple[int | None, float | None]]:
    result = {}
    for row in rows:
        prediction = next(
            (
                _optional_binary(row.get(column))
                for column in PREDICTION_COLUMNS
                if column in row
            ),
            None,
        )
        if str(row.get("status", "success")).strip().lower() not in {
            "",
            "success",
        }:
            continue
        result[_key(row)] = (prediction, _optional_float(row.get("score")))
    return result


def _status_text(row: dict[str, str]) -> str:
    fields = (
        "failure_type",
        "failure_status",
        "status",
        "fallback_400_status",
        "preprocessing_fallback_status",
    )
    return " ".join(str(row.get(field, "")).strip().lower() for field in fields)


def _failure_keys(rows: Iterable[dict[str, str]]) -> set[tuple[str, int]]:
    return {
        _key(row)
        for row in rows
        if any(value in _status_text(row) for value in FAILURE_VALUES)
    }


def _recovered_keys(rows: Iterable[dict[str, str]]) -> set[tuple[str, int]]:
    recovered = set()
    for row in rows:
        status = _status_text(row)
        has_output = any(
            str(row.get(column, "")).strip()
            for column in (
                "fallback_400_mxl_path",
                "fallback_400_midi_path",
                "preprocessing_mxl_path",
                "preprocessing_midi_path",
            )
        )
        if has_output or any(value in status for value in RECOVERED_VALUES):
            if "still_failed" not in status:
                recovered.add(_key(row))
    return recovered


def _existing_image_path(
    pages_dir: Path,
    doc_id: str,
    page_index: int,
) -> Path | None:
    page_stem = f"page_{page_index:03d}"
    document_dir = pages_dir / doc_id
    for suffix in (".png", ".jpg", ".jpeg"):
        candidate = document_dir / f"{page_stem}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def _reason_group(reasons: list[str]) -> str:
    return min(reasons, key=lambda value: GROUP_PRIORITY[value])


def build_omr_eval_sample(
    labels_rows: Iterable[dict[str, str]],
    *,
    pages_dir: Path,
    cnn_rows: Iterable[dict[str, str]] = (),
    classical_rows: Iterable[dict[str, str]] = (),
    failure_rows: Iterable[dict[str, str]] = (),
    fallback_rows: Iterable[dict[str, str]] = (),
    sample_size: int = 300,
    random_seed: int = 42,
    low_confidence_threshold: float = 0.95,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Build a priority-first sample and fill remaining slots randomly."""
    if sample_size < 0:
        raise ValueError("sample_size must be zero or positive")

    cnn = _prediction_map(cnn_rows)
    classical = _prediction_map(classical_rows)
    failures = _failure_keys(failure_rows)
    recovered = _recovered_keys(fallback_rows)

    labels_by_key: dict[tuple[str, int], dict[str, str]] = {}
    for row in labels_rows:
        labels_by_key.setdefault(_key(row), dict(row))

    all_keys = set(labels_by_key) | set(cnn) | set(classical) | failures | recovered
    candidates: list[dict[str, object]] = []
    missing_images = 0
    for doc_id, page_index in sorted(all_keys):
        image_path = _existing_image_path(pages_dir, doc_id, page_index)
        if image_path is None:
            missing_images += 1
            continue

        label = labels_by_key.get((doc_id, page_index), {})
        page_type = str(label.get("page_type", "")).strip().lower()
        manual = _optional_binary(
            label.get("has_music", label.get("has_music_manual", ""))
        )
        cnn_prediction, cnn_score = cnn.get((doc_id, page_index), (None, None))
        classical_prediction, classical_score = classical.get(
            (doc_id, page_index), (None, None)
        )
        key = (doc_id, page_index)
        likely_music = (
            page_type in ELIGIBLE_PAGE_TYPES
            or manual == 1
            or cnn_prediction == 1
            or classical_prediction == 1
            or key in failures
            or key in recovered
        )
        if not likely_music:
            continue

        reasons = []
        if key in failures:
            reasons.append("previous_omr_failure")
        if key in recovered:
            reasons.append("fallback_recovered")
        if (
            cnn_prediction is not None
            and classical_prediction is not None
            and cnn_prediction != classical_prediction
        ):
            reasons.append("model_disagreement")
        if page_type == "mixed":
            reasons.append("mixed_page")
        scores = [
            score
            for score in (cnn_score, classical_score)
            if score is not None
        ]
        if scores and min(scores) < low_confidence_threshold:
            reasons.append("low_confidence_candidate")
        if not reasons:
            reasons.append("random_music")

        candidates.append(
            {
                "doc_id": doc_id,
                "page_index": page_index,
                "image_path": str(image_path),
                "page_type": page_type or "unknown",
                "has_music_manual": "" if manual is None else manual,
                "cnn_prediction": (
                    "" if cnn_prediction is None else cnn_prediction
                ),
                "classical_prediction": (
                    "" if classical_prediction is None else classical_prediction
                ),
                "sample_group": _reason_group(reasons),
                "source_reason": ";".join(reasons),
            }
        )

    generator = random.Random(random_seed)
    priority_rows = [
        row for row in candidates if row["sample_group"] != "random_music"
    ]
    random_rows = [
        row for row in candidates if row["sample_group"] == "random_music"
    ]
    priority_rows.sort(
        key=lambda row: (
            GROUP_PRIORITY[str(row["sample_group"])],
            str(row["doc_id"]),
            int(row["page_index"]),
        )
    )
    generator.shuffle(random_rows)

    selected = (priority_rows + random_rows)[:sample_size]
    selected.sort(key=lambda row: (str(row["doc_id"]), int(row["page_index"])))
    summary = {
        "eligible_pages": len(candidates),
        "sampled_pages": len(selected),
        "documents": len({str(row["doc_id"]) for row in selected}),
        "group_counts": Counter(str(row["sample_group"]) for row in selected),
        "page_type_counts": Counter(str(row["page_type"]) for row in selected),
        "all_image_paths_exist": all(
            Path(str(row["image_path"])).is_file() for row in selected
        ),
        "missing_image_candidates": missing_images,
        "random_seed": random_seed,
        "sample_size_requested": sample_size,
        "warning": (
            f"Only {len(selected)} eligible pages with existing images were found."
            if len(selected) < sample_size
            else ""
        ),
    }
    return selected, summary


def write_sample_csv(rows: list[dict[str, object]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(summary: dict[str, object], summary_path: Path) -> None:
    group_counts = Counter(summary["group_counts"])
    page_type_counts = Counter(summary["page_type_counts"])
    lines = [
        "# OMR evaluation sample: 300 pages",
        "",
        f"- Requested pages: {summary['sample_size_requested']}",
        f"- Total sampled pages: {summary['sampled_pages']}",
        f"- Eligible pages with existing images: {summary['eligible_pages']}",
        f"- Documents: {summary['documents']}",
        f"- All image paths exist: {summary['all_image_paths_exist']}",
        f"- Candidates skipped because image was missing: {summary['missing_image_candidates']}",
        f"- Random seed: {summary['random_seed']}",
        "",
        "## Sample groups",
        "",
        "| Group | Pages |",
        "|---|---:|",
    ]
    lines.extend(
        f"| {group} | {group_counts[group]} |"
        for group in sorted(group_counts, key=lambda value: GROUP_PRIORITY[value])
    )
    lines.extend(
        [
            "",
            "## Page types",
            "",
            "| Page type | Pages |",
            "|---|---:|",
        ]
    )
    lines.extend(
        f"| {page_type} | {count} |"
        for page_type, count in sorted(page_type_counts.items())
    )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- The sample prioritizes technical failures, model disagreements, "
            "mixed pages and low-confidence predictions; it is not a purely "
            "random estimate of the complete corpus.",
            "- Classifier predictions are candidate signals, not ground truth.",
            "- Existing PNG files are required, so incomplete documents are excluded.",
            "- Technical MXL/MIDI generation does not measure musical correctness.",
        ]
    )
    if summary["warning"]:
        lines.extend(["", f"**Warning:** {summary['warning']}"])
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--pages-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument(
        "--cnn-predictions",
        type=Path,
        default=Path(
            "outputs/reports/page_classifier/"
            "cnn_has_music_all_pages_predictions.csv"
        ),
    )
    parser.add_argument(
        "--classical-predictions",
        type=Path,
        default=Path(
            "outputs/reports/page_classifier/"
            "classical_has_music_all_pages_predictions.csv"
        ),
    )
    parser.add_argument(
        "--failure-report",
        type=Path,
        default=Path("outputs/reports/omr_failure_report.csv"),
    )
    parser.add_argument(
        "--fallback-report",
        type=Path,
        action="append",
        default=None,
    )
    parser.add_argument("--sample-size", "--limit", type=int, default=300)
    parser.add_argument("--random-seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    fallback_paths = args.fallback_report or [
        Path("outputs/reports/omr_400dpi_fallback_report.csv"),
        Path("outputs/reports/omr_preprocessing_fallback_report.csv"),
    ]
    try:
        labels_rows = _read_csv(args.labels, required=True)
        fallback_rows = [
            row for path in fallback_paths for row in _read_csv(path)
        ]
        sample, summary = build_omr_eval_sample(
            labels_rows,
            pages_dir=args.pages_dir,
            cnn_rows=_read_csv(args.cnn_predictions),
            classical_rows=_read_csv(args.classical_predictions),
            failure_rows=_read_csv(args.failure_report),
            fallback_rows=fallback_rows,
            sample_size=args.sample_size,
            random_seed=args.random_seed,
        )
        write_sample_csv(sample, args.out)
        write_summary(summary, args.summary)
    except (FileNotFoundError, ValueError, OSError, csv.Error) as error:
        raise SystemExit(f"Error: {error}") from error

    print(f"Eligible pages: {summary['eligible_pages']}")
    print(f"Sample pages: {summary['sampled_pages']}")
    print(f"Documents: {summary['documents']}")
    print("Groups:")
    for group, count in sorted(
        Counter(summary["group_counts"]).items(),
        key=lambda item: GROUP_PRIORITY[item[0]],
    ):
        print(f"  {group}: {count}")
    if summary["warning"]:
        print(f"Warning: {summary['warning']}")
    print(f"Output: {args.out}")
    print(f"Summary: {args.summary}")


if __name__ == "__main__":
    main()
