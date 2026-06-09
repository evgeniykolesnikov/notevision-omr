"""Calculate expert MusicXML review metrics from the review_app CSV export."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Iterable

PROBLEM_FIELDS = (
    "pitch_problem",
    "rhythm_problem",
    "missing_notes_problem",
    "extra_notes_problem",
    "chord_problem",
    "voice_problem",
    "measure_structure_problem",
    "playback_problem",
    "unreadable_or_failed",
)
NUMERIC_FIELDS = (
    "checked_measures",
    "correct_measures",
    "reference_notes",
    "matched_notes",
    "pitch_errors",
    "duration_errors",
    "missing_notes",
    "extra_notes",
)
REQUIRED_COLUMNS = {
    "doc_id",
    "page_index",
    "reviewer",
    "review_status",
    "page_usable",
    "usability_score",
    *PROBLEM_FIELDS,
    *NUMERIC_FIELDS,
}
METRICS_COLUMNS = (
    "section",
    "metric",
    "doc_id",
    "page_index",
    "value",
    "numerator",
    "denominator",
    "notes",
)


def _optional_float(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError as error:
        raise ValueError(f"Expected a number or an empty value, got {text!r}") from error


def _flag(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _reviewer_key(row: dict[str, str]) -> str:
    reviewer_id = str(row.get("reviewer_id", "")).strip()
    if reviewer_id:
        return f"id:{reviewer_id}"
    reviewer = " ".join(str(row.get("reviewer", "")).split()).casefold()
    return f"name:{reviewer}" if reviewer else ""


def _normalized_reviewer_name(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()


def filter_review_rows(
    rows: list[dict[str, str]],
    *,
    completed_only: bool = False,
    exclude_reviewers: Iterable[str] = (),
) -> tuple[list[dict[str, str]], list[str]]:
    """Apply report filters and return rows plus matched exclusions."""
    requested_exclusions: dict[str, str] = {}
    for name in exclude_reviewers:
        normalized = _normalized_reviewer_name(name)
        if normalized and normalized not in requested_exclusions:
            requested_exclusions[normalized] = " ".join(str(name).split())
    excluded_names = set(requested_exclusions)
    for row in rows:
        reviewer_name = str(row.get("reviewer", "")).strip()
        normalized = _normalized_reviewer_name(reviewer_name)
        if normalized in requested_exclusions and reviewer_name:
            requested_exclusions[normalized] = reviewer_name
    filtered = [
        row
        for row in rows
        if _normalized_reviewer_name(row.get("reviewer")) not in excluded_names
        and (
            not completed_only
            or row.get("review_status", "").strip() == "completed"
        )
    ]
    return filtered, sorted(requested_exclusions.values(), key=str.casefold)


def _page_key(row: dict[str, str]) -> tuple[str, int]:
    doc_id = str(row.get("doc_id", "")).strip()
    try:
        page_index = int(float(str(row.get("page_index", "")).strip()))
    except ValueError as error:
        raise ValueError(
            f"Invalid page_index for {doc_id or '<empty document>'}: "
            f"{row.get('page_index', '')!r}"
        ) from error
    if not doc_id or page_index < 1:
        raise ValueError("Every review must have a doc_id and positive page_index")
    return doc_id, page_index


def read_review_export(path: Path) -> list[dict[str, str]]:
    """Read and validate a CSV export produced by review_app."""
    if not path.is_file():
        raise FileNotFoundError(f"Expert review CSV does not exist: {path}")
    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        missing = sorted(REQUIRED_COLUMNS - set(reader.fieldnames or []))
        if missing:
            raise ValueError(
                "Expert review CSV is missing required columns: "
                + ", ".join(missing)
            )
        rows = list(reader)

    for row in rows:
        _page_key(row)
        for field in NUMERIC_FIELDS:
            _optional_float(row.get(field))
        _optional_float(row.get("usability_score"))
    return rows


def _micro_ratio(
    rows: Iterable[dict[str, str]],
    numerator_fields: tuple[str, ...],
    denominator_field: str,
) -> dict[str, float | int] | None:
    numerator = 0.0
    denominator = 0.0
    used_rows = 0
    for row in rows:
        values = [_optional_float(row.get(field)) for field in numerator_fields]
        denominator_value = _optional_float(row.get(denominator_field))
        if denominator_value is None or denominator_value <= 0:
            continue
        if any(value is None for value in values):
            continue
        numerator += sum(value for value in values if value is not None)
        denominator += denominator_value
        used_rows += 1
    if not used_rows or denominator <= 0:
        return None
    return {
        "value": numerator / denominator,
        "numerator": numerator,
        "denominator": denominator,
        "rows": used_rows,
    }


def analyze_expert_reviews(rows: list[dict[str, str]]) -> dict[str, object]:
    """Build progress, quality, quantitative, and disagreement metrics."""
    reviewers = {_reviewer_key(row) for row in rows if _reviewer_key(row)}
    reviewed_rows = [
        row
        for row in rows
        if row.get("review_status", "").strip() in {"draft", "completed"}
    ]
    completed = [
        row for row in rows if row.get("review_status", "").strip() == "completed"
    ]
    statuses = {
        status: sum(row.get("review_status", "").strip() == status for row in rows)
        for status in ("completed", "draft", "not_reviewed")
    }
    usable_counts = {
        value: sum(
            row.get("page_usable", "").strip().lower() == value for row in completed
        )
        for value in ("yes", "partial", "no")
    }
    scores = [
        score
        for row in completed
        if (score := _optional_float(row.get("usability_score"))) is not None
    ]
    reviewer_score_values: defaultdict[str, list[float]] = defaultdict(list)
    for row in completed:
        score = _optional_float(row.get("usability_score"))
        reviewer_name = str(row.get("reviewer", "")).strip()
        if reviewer_name and score is not None:
            reviewer_score_values[reviewer_name].append(score)
    reviewer_mean_scores = {
        reviewer: mean(values)
        for reviewer, values in sorted(
            reviewer_score_values.items(),
            key=lambda item: item[0].casefold(),
        )
    }
    problem_rates = {
        field: {
            "count": sum(_flag(row.get(field)) for row in completed),
            "denominator": len(completed),
            "rate": (
                sum(_flag(row.get(field)) for row in completed) / len(completed)
                if completed
                else None
            ),
        }
        for field in PROBLEM_FIELDS
    }
    quantitative = {
        "measure_accuracy": _micro_ratio(
            completed, ("correct_measures",), "checked_measures"
        ),
        "note_event_error_rate": _micro_ratio(
            completed,
            ("pitch_errors", "duration_errors", "missing_notes", "extra_notes"),
            "reference_notes",
        ),
        "pitch_error_rate": _micro_ratio(
            completed, ("pitch_errors",), "matched_notes"
        ),
        "duration_error_rate": _micro_ratio(
            completed, ("duration_errors",), "matched_notes"
        ),
        "missing_note_rate": _micro_ratio(
            completed, ("missing_notes",), "reference_notes"
        ),
        "extra_note_rate": _micro_ratio(
            completed, ("extra_notes",), "reference_notes"
        ),
    }

    grouped: defaultdict[tuple[str, int], list[dict[str, str]]] = defaultdict(list)
    for row in completed:
        grouped[_page_key(row)].append(row)
    disagreements = []
    for (doc_id, page_index), page_rows in grouped.items():
        page_reviewers = {
            _reviewer_key(row) for row in page_rows if _reviewer_key(row)
        }
        if len(page_reviewers) < 2:
            continue
        usable_values = sorted(
            {
                row.get("page_usable", "").strip().lower()
                for row in page_rows
                if row.get("page_usable", "").strip()
            }
        )
        page_scores = [
            score
            for row in page_rows
            if (score := _optional_float(row.get("usability_score"))) is not None
        ]
        score_range = max(page_scores) - min(page_scores) if len(page_scores) >= 2 else None
        disagreements.append(
            {
                "doc_id": doc_id,
                "page_index": page_index,
                "reviewers_count": len(page_reviewers),
                "page_usable_values": usable_values,
                "page_usable_disagreement": len(usable_values) > 1,
                "usability_scores": sorted(page_scores),
                "usability_score_range": score_range,
            }
        )
    disagreements.sort(
        key=lambda row: (
            -(row["usability_score_range"] or 0),
            -int(row["page_usable_disagreement"]),
            row["doc_id"],
            row["page_index"],
        )
    )

    return {
        "experts_count": len(reviewers),
        "review_records": len(rows),
        "reviewed_pages": len({_page_key(row) for row in reviewed_rows}),
        "statuses": statuses,
        "completed_rows": len(completed),
        "usable_counts": usable_counts,
        "mean_usability_score": mean(scores) if scores else None,
        "usability_score_count": len(scores),
        "reviewer_mean_scores": reviewer_mean_scores,
        "included_reviewers": sorted(
            {
                str(row.get("reviewer", "")).strip()
                for row in rows
                if str(row.get("reviewer", "")).strip()
            },
            key=str.casefold,
        ),
        "problem_rates": problem_rates,
        "quantitative": quantitative,
        "multi_reviewer_pages": len(disagreements),
        "usable_disagreement_pages": sum(
            bool(row["page_usable_disagreement"]) for row in disagreements
        ),
        "score_disagreement_pages": sum(
            (row["usability_score_range"] or 0) > 0 for row in disagreements
        ),
        "disagreements": disagreements,
    }


def build_metrics_rows(analysis: dict[str, object]) -> list[dict[str, object]]:
    """Convert the analysis into a machine-readable long-form table."""
    rows: list[dict[str, object]] = []

    def add(
        section: str,
        metric: str,
        value: object,
        numerator: object = "",
        denominator: object = "",
        notes: str = "",
        doc_id: str = "",
        page_index: object = "",
    ) -> None:
        rows.append(
            {
                "section": section,
                "metric": metric,
                "doc_id": doc_id,
                "page_index": page_index,
                "value": "" if value is None else value,
                "numerator": numerator,
                "denominator": denominator,
                "notes": notes,
            }
        )

    add("overview", "experts_count", analysis["experts_count"])
    add("overview", "reviewed_pages", analysis["reviewed_pages"])
    add("overview", "review_records", analysis["review_records"])
    for status, count in analysis["statuses"].items():
        add("progress", status, count)
    for value, count in analysis["usable_counts"].items():
        add("page_usable", value, count)
    add(
        "quality",
        "mean_usability_score",
        analysis["mean_usability_score"],
        denominator=analysis["usability_score_count"],
        notes="Completed reviews with a non-empty score",
    )
    for field, result in analysis["problem_rates"].items():
        add(
            "problem_rate",
            field,
            result["rate"],
            result["count"],
            result["denominator"],
            "Share of completed reviews",
        )
    for metric, result in analysis["quantitative"].items():
        if result is None:
            add(
                "quantitative",
                metric,
                None,
                notes="Not enough populated quantitative fields",
            )
        else:
            add(
                "quantitative",
                metric,
                result["value"],
                result["numerator"],
                result["denominator"],
                f"Micro-average over {result['rows']} completed review(s)",
            )
    add("agreement", "multi_reviewer_pages", analysis["multi_reviewer_pages"])
    add(
        "agreement",
        "page_usable_disagreement_pages",
        analysis["usable_disagreement_pages"],
    )
    add(
        "agreement",
        "usability_score_disagreement_pages",
        analysis["score_disagreement_pages"],
    )
    for disagreement in analysis["disagreements"]:
        add(
            "disagreement",
            "reviewer_disagreement",
            disagreement["usability_score_range"],
            notes=(
                "page_usable="
                + "|".join(disagreement["page_usable_values"])
                + "; usability_scores="
                + "|".join(str(value) for value in disagreement["usability_scores"])
                + f"; reviewers={disagreement['reviewers_count']}"
            ),
            doc_id=disagreement["doc_id"],
            page_index=disagreement["page_index"],
        )
    return rows


def _format_metric(value: object, percent: bool = False) -> str:
    if value is None:
        return "н/д"
    return f"{float(value):.2%}" if percent else f"{float(value):.3f}"


def build_summary_markdown(analysis: dict[str, object]) -> str:
    """Create a thesis-ready Markdown summary with explicit formulas."""
    statuses = analysis["statuses"]
    usable = analysis["usable_counts"]
    completed = int(analysis["completed_rows"])
    problem_rows = "\n".join(
        f"| `{field}` | {result['count']} | "
        f"{_format_metric(result['rate'], percent=True)} |"
        for field, result in analysis["problem_rates"].items()
    )
    quantitative_rows = "\n".join(
        f"| `{metric}` | "
        f"{_format_metric(result['value'], percent=True) if result else 'н/д'} | "
        f"{result['numerator'] if result else ''} | "
        f"{result['denominator'] if result else ''} |"
        for metric, result in analysis["quantitative"].items()
    )
    disagreement_rows = "\n".join(
        f"| `{row['doc_id']}` | {row['page_index']} | "
        f"{', '.join(row['page_usable_values']) or 'н/д'} | "
        f"{', '.join(str(value) for value in row['usability_scores']) or 'н/д'} | "
        f"{_format_metric(row['usability_score_range'])} |"
        for row in analysis["disagreements"][:10]
    )
    if not disagreement_rows:
        disagreement_rows = "| Нет страниц с несколькими завершёнными оценками |  |  |  |  |"
    reviewer_score_rows = "\n".join(
        f"| {reviewer} | {_format_metric(score)} |"
        for reviewer, score in analysis["reviewer_mean_scores"].items()
    )
    if not reviewer_score_rows:
        reviewer_score_rows = "| Нет завершённых оценок | н/д |"
    included_reviewers = ", ".join(analysis["included_reviewers"]) or "нет"
    excluded_reviewers = ", ".join(
        analysis.get("excluded_reviewers", [])
    ) or "нет"

    return f"""# Экспертная оценка качества OMR

Отчёт рассчитан по CSV-экспорту `review_app`. Качественные и количественные
метрики ниже используют только отзывы со статусом `completed`; черновики
учитываются только в статистике прогресса.

Технический результат pipeline **141/150 (94%)** означает наличие созданных
MXL/MIDI-файлов и **не входит** в расчёт экспертной музыкальной точности.

## Охват и прогресс

| Показатель | Значение |
|---|---:|
| Экспертов | {analysis['experts_count']} |
| Уникальных страниц с draft/completed | {analysis['reviewed_pages']} |
| Записей completed | {statuses['completed']} |
| Записей draft | {statuses['draft']} |
| Явных записей not_reviewed | {statuses['not_reviewed']} |

CSV-экспорт web app обычно содержит только созданные отзывы. Поэтому
`not_reviewed` отражает только явно экспортированные строки с таким статусом,
а не число всех неназначенных экспертам страниц.

## Пригодность результата

| page_usable | Количество |
|---|---:|
| yes | {usable['yes']} |
| partial | {usable['partial']} |
| no | {usable['no']} |

Средняя оценка `usability_score`: **{_format_metric(analysis['mean_usability_score'])}**
по {analysis['usability_score_count']} завершённым отзывам с заполненной оценкой.

### Средняя оценка по экспертам

| Эксперт | Средний usability_score |
|---|---:|
{reviewer_score_rows}

Включённые эксперты: {included_reviewers}.

Исключённые эксперты: {excluded_reviewers}.

## Отмеченные проблемы

Доля рассчитывается как число завершённых отзывов с установленным флагом,
делённое на общее число завершённых отзывов ({completed}).

| Тип проблемы | Отмечено | Доля |
|---|---:|---:|
{problem_rows}

## Количественные метрики

Пустые поля исключаются попарно и не интерпретируются как нули. Используются
микроусреднённые суммы:

- `measure_accuracy = Σ correct_measures / Σ checked_measures`;
- `note_event_error_rate = Σ(pitch_errors + duration_errors + missing_notes + extra_notes) / Σ reference_notes`;
- `pitch_error_rate = Σ pitch_errors / Σ matched_notes`;
- `duration_error_rate = Σ duration_errors / Σ matched_notes`;
- `missing_note_rate = Σ missing_notes / Σ reference_notes`;
- `extra_note_rate = Σ extra_notes / Σ reference_notes`.

`note_event_error_rate` является операционным показателем и может превышать
100%, если для одного эталонного события отмечено несколько типов ошибок.

| Метрика | Значение | Числитель | Знаменатель |
|---|---:|---:|---:|
{quantitative_rows}

## Межэкспертные расхождения

Страниц с завершёнными отзывами нескольких экспертов:
**{analysis['multi_reviewer_pages']}**. Расхождение по `page_usable` найдено для
**{analysis['usable_disagreement_pages']}** страниц, по `usability_score` — для
**{analysis['score_disagreement_pages']}** страниц.

Ниже приведены до 10 страниц с максимальным диапазоном оценок; при равном
диапазоне выше располагаются страницы с различающимся `page_usable`.

| doc_id | page_index | page_usable | usability_score | Диапазон score |
|---|---:|---|---|---:|
{disagreement_rows}
"""


def write_expert_review_reports(
    input_path: Path,
    metrics_path: Path,
    summary_path: Path,
    *,
    completed_only: bool = False,
    exclude_reviewers: Iterable[str] = (),
) -> dict[str, object]:
    """Calculate metrics and write CSV plus Markdown reports."""
    rows, matched_exclusions = filter_review_rows(
        read_review_export(input_path),
        completed_only=completed_only,
        exclude_reviewers=exclude_reviewers,
    )
    analysis = analyze_expert_reviews(rows)
    analysis["excluded_reviewers"] = matched_exclusions
    analysis["completed_only"] = completed_only
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with metrics_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=METRICS_COLUMNS)
        writer.writeheader()
        writer.writerows(build_metrics_rows(analysis))
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(build_summary_markdown(analysis), encoding="utf-8")
    return analysis


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument(
        "--metrics-out",
        type=Path,
        default=Path("outputs/reports/expert_review_metrics.csv"),
    )
    parser.add_argument(
        "--summary-out",
        type=Path,
        default=Path("outputs/reports/expert_review_summary.md"),
    )
    parser.add_argument(
        "--completed-only",
        action="store_true",
        help="Analyze only completed reviews.",
    )
    parser.add_argument(
        "--exclude-reviewer",
        action="append",
        default=[],
        help="Reviewer name to exclude; repeat for multiple reviewers.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        analysis = write_expert_review_reports(
            args.input,
            args.metrics_out,
            args.summary_out,
            completed_only=args.completed_only,
            exclude_reviewers=args.exclude_reviewer,
        )
    except (FileNotFoundError, ValueError, OSError, csv.Error) as error:
        raise SystemExit(f"Error: {error}") from error

    print(f"Experts: {analysis['experts_count']}")
    print(f"Reviewed pages: {analysis['reviewed_pages']}")
    print(f"Completed: {analysis['statuses']['completed']}")
    print(f"Draft: {analysis['statuses']['draft']}")
    print(f"Metrics: {args.metrics_out}")
    print(f"Summary: {args.summary_out}")


if __name__ == "__main__":
    main()
