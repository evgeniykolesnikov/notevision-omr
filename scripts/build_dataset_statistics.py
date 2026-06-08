"""Build thesis dataset statistics and a Markdown dataset report."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

from evaluate_music_detector import evaluate_music_detector_rows

PAGE_TYPES = ("music", "mixed", "title", "text", "blank", "bad_scan", "unknown")
STATISTICS_COLUMNS = ["total_pages", *PAGE_TYPES]
REQUIRED_COLUMNS = {
    "doc_id",
    "page_type",
    "has_music",
    "has_music_pred",
}


def build_dataset_statistics(
    labels_rows: list[dict[str, str]],
) -> dict[str, int]:
    """Count pages overall and by the thesis page-type taxonomy."""
    counts = Counter(row.get("page_type", "").strip().lower() for row in labels_rows)
    return {
        "total_pages": len(labels_rows),
        **{page_type: counts[page_type] for page_type in PAGE_TYPES},
    }


def read_labels(path: Path) -> list[dict[str, str]]:
    """Read labels and validate fields needed by statistics and error analysis."""
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


def write_dataset_statistics(
    labels_path: Path,
    output_path: Path,
) -> tuple[dict[str, int], list[dict[str, str]]]:
    """Save one-row dataset statistics and return the source labels."""
    labels_rows = read_labels(labels_path)
    statistics = build_dataset_statistics(labels_rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=STATISTICS_COLUMNS)
        writer.writeheader()
        writer.writerow(statistics)
    return statistics, labels_rows


def _top_error_documents(
    labels_rows: list[dict[str, str]],
    limit: int = 5,
) -> list[tuple[str, int, int]]:
    errors: defaultdict[str, list[int]] = defaultdict(lambda: [0, 0])
    for row in labels_rows:
        actual = int(float(row["has_music"]))
        predicted = int(float(row["has_music_pred"]))
        if actual == 0 and predicted == 1:
            errors[row["doc_id"]][0] += 1
        elif actual == 1 and predicted == 0:
            errors[row["doc_id"]][1] += 1
    ranked = sorted(
        (
            (doc_id, counts[0], counts[1])
            for doc_id, counts in errors.items()
        ),
        key=lambda item: (-(item[1] + item[2]), item[0]),
    )
    return ranked[:limit]


def build_dataset_markdown(
    statistics: dict[str, int],
    labels_rows: list[dict[str, str]],
    labels_path: Path,
) -> str:
    """Create a factual thesis dataset chapter from the current labels."""
    total = statistics["total_pages"]
    documents = len({row["doc_id"] for row in labels_rows})
    metrics = evaluate_music_detector_rows(labels_rows)
    class_rows = "\n".join(
        f"| `{page_type}` | {statistics[page_type]} | "
        f"{(statistics[page_type] / total * 100 if total else 0):.2f}% |"
        for page_type in PAGE_TYPES
    )
    top_errors = _top_error_documents(labels_rows)
    if top_errors:
        top_error_rows = "\n".join(
            f"| `{doc_id}` | {fp} | {fn} | {fp + fn} |"
            for doc_id, fp, fn in top_errors
        )
    else:
        top_error_rows = "| Нет ошибок | 0 | 0 | 0 |"

    return f"""# Статистика корпуса NoteVision OMR

Документ сформирован автоматически на основе `{labels_path.as_posix()}`.

## Размер корпуса

В текущую валидированную выборку ВКР входят **{documents} документ(а/ов)** и
**{total} страниц**. Единицей оценки detector является отдельная страница.
Истинный класс берётся из `has_music`, прогноз — из `has_music_pred`.

## Распределение классов

| Тип страницы | Количество | Доля |
|---|---:|---:|
{class_rows}

Сумма классов в таблице равна {sum(statistics[key] for key in PAGE_TYPES)}.
Страницы `mixed` учитываются отдельно от `music`, но в бинарной оценке могут
иметь `has_music = 1`.

## Источники данных

Корпус сформирован из PDF-сканов и MRC/MARC-записей цифровой библиотеки.
Исходные PDF/MRC обрабатываются локально в `data/raw/<doc_id>/` и не
публикуются в Git. Воспроизводимая часть корпуса представлена CSV-разметкой,
инвентаризацией документов, кодом обработки и агрегированными отчётами.

## Типичные ошибки detector

На текущей разметке получены:

- TP: **{metrics['tp']}**;
- FP: **{metrics['fp']}**;
- TN: **{metrics['tn']}**;
- FN: **{metrics['fn']}**;
- accuracy: **{metrics['accuracy']:.4f}**;
- precision: **{metrics['precision']:.4f}**;
- recall: **{metrics['recall']:.4f}**;
- F1: **{metrics['f1']:.4f}**.

Документы с наибольшим числом ошибок:

| doc_id | False positive | False negative | Всего ошибок |
|---|---:|---:|---:|
{top_error_rows}

False positive означает, что detector принял ненотную страницу за нотную.
False negative означает, что валидированная нотная страница не была отобрана.
Постраничные примеры сохраняются в `outputs/reports/error_analysis.csv` и
просматриваются через `outputs/reports/error_gallery.html`.

## Ограничения корпуса

- Корпус ограничен текущим набором цифровых документов и может не отражать
  всё разнообразие изданий, типов печати и качества сканирования.
- Разметка выполнялась частично вручную; спорные страницы и класс `unknown`
  требуют дальнейшей экспертной проверки.
- Бинарная page-level разметка не является symbol-level ground truth и не
  измеряет точность распознавания нот, длительностей, голосов и тактов.
- Технически успешное создание MXL/MIDI не доказывает музыкальную
  корректность результата.
- Значения метрик относятся только к текущей версии разметки и detector.
"""


def write_dataset_markdown(
    markdown_path: Path,
    statistics: dict[str, int],
    labels_rows: list[dict[str, str]],
    labels_path: Path,
) -> None:
    """Save the generated thesis dataset chapter."""
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(
        build_dataset_markdown(statistics, labels_rows, labels_path),
        encoding="utf-8",
    )


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
        default=Path("outputs/reports/dataset_statistics.csv"),
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        default=Path("docs/thesis/dataset_statistics.md"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        statistics, labels_rows = write_dataset_statistics(args.labels, args.out)
        write_dataset_markdown(
            args.markdown_out,
            statistics,
            labels_rows,
            args.labels,
        )
    except (FileNotFoundError, ValueError, OSError, csv.Error) as error:
        raise SystemExit(f"Error: {error}") from error

    print(f"Documents: {len({row['doc_id'] for row in labels_rows})}")
    print(f"Total pages: {statistics['total_pages']}")
    for page_type in PAGE_TYPES:
        print(f"{page_type}: {statistics[page_type]}")
    print(f"Statistics: {args.out}")
    print(f"Dataset report: {args.markdown_out}")


if __name__ == "__main__":
    main()
