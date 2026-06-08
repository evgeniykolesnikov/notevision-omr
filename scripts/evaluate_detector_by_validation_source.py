"""Evaluate music-page detector metrics by label validation source."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterable

from evaluate_music_detector import evaluate_music_detector_rows

GROUP_MANUAL_PREVIOUS = "manual_previous"
GROUP_MANUAL_THESIS = "manual_thesis"
GROUP_MANUAL_ALL = "manual_all"
GROUP_TEMPLATE = "template_prediction"
GROUP_ALL = "all"
GROUP_ORDER = [
    GROUP_MANUAL_PREVIOUS,
    GROUP_MANUAL_THESIS,
    GROUP_MANUAL_ALL,
    GROUP_TEMPLATE,
    GROUP_ALL,
]
MANUAL_SOURCES = {GROUP_MANUAL_PREVIOUS, GROUP_MANUAL_THESIS}

REPORT_COLUMNS = [
    "group",
    "rows",
    "tp",
    "fp",
    "tn",
    "fn",
    "accuracy",
    "precision",
    "recall",
    "f1",
]
REQUIRED_COLUMNS = {
    "has_music",
    "has_music_pred",
    "validation_source",
}


def read_labels(path: Path) -> list[dict[str, str]]:
    """Read validated labels and verify fields required for grouped metrics."""
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


def _select_group(
    rows: list[dict[str, str]],
    group: str,
) -> list[dict[str, str]]:
    if group == GROUP_ALL:
        return rows
    if group == GROUP_MANUAL_ALL:
        return [
            row
            for row in rows
            if str(row.get("validation_source", "")).strip()
            in MANUAL_SOURCES
        ]
    return [
        row
        for row in rows
        if str(row.get("validation_source", "")).strip() == group
    ]


def evaluate_detector_by_validation_source(
    labels_rows: Iterable[dict[str, str]],
) -> list[dict[str, int | float | str]]:
    """Calculate metrics for manual, template, and complete-corpus slices."""
    rows = list(labels_rows)
    if not rows:
        raise ValueError("Labels CSV contains no rows to evaluate")

    report: list[dict[str, int | float | str]] = []
    for group in GROUP_ORDER:
        selected = _select_group(rows, group)
        if not selected:
            raise ValueError(f"Validation group contains no rows: {group}")
        metrics = evaluate_music_detector_rows(selected)
        report.append(
            {
                "group": group,
                "rows": len(selected),
                **metrics,
            }
        )
    return report


def write_validation_source_report(
    labels_path: Path,
    output_path: Path,
) -> list[dict[str, int | float | str]]:
    """Evaluate and save all validation-source slices."""
    report = evaluate_detector_by_validation_source(read_labels(labels_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(report)
    return report


def _by_group(
    report: list[dict[str, int | float | str]],
) -> dict[str, dict[str, int | float | str]]:
    return {str(row["group"]): row for row in report}


def build_validation_bias_markdown(
    report: list[dict[str, int | float | str]],
    labels_path: Path,
) -> str:
    """Generate a thesis-ready explanation of validation-source bias."""
    groups = _by_group(report)
    all_metrics = groups[GROUP_ALL]
    manual_metrics = groups[GROUP_MANUAL_ALL]
    template_metrics = groups[GROUP_TEMPLATE]
    f1_all = float(all_metrics["f1"])
    f1_manual = float(manual_metrics["f1"])
    absolute_gap = f1_all - f1_manual
    relative_increase = (
        absolute_gap / f1_manual if f1_manual else 0.0
    )
    template_share = int(template_metrics["rows"]) / int(all_metrics["rows"])

    table_rows = "\n".join(
        f"| `{group}` | {int(groups[group]['rows'])} | "
        f"{int(groups[group]['tp'])} | {int(groups[group]['fp'])} | "
        f"{int(groups[group]['tn'])} | {int(groups[group]['fn'])} | "
        f"{float(groups[group]['accuracy']):.4f} | "
        f"{float(groups[group]['precision']):.4f} | "
        f"{float(groups[group]['recall']):.4f} | "
        f"{float(groups[group]['f1']):.4f} |"
        for group in GROUP_ORDER
    )

    return f"""# Влияние источника валидации на метрики detector

Документ сформирован по текущему файлу `{labels_path.as_posix()}`.

## Цель проверки

Часть thesis-разметки была создана переносом ручных меток, а часть —
автоматически инициализирована значением `has_music_pred`. Если такие
автоматически подтверждённые строки использовать как ground truth, detector
оценивается на метках, происходящих от его собственного прогноза. Цель анализа
— отдельно показать метрики на ручных и автоматически созданных группах.

## Результаты

| Группа | Страницы | TP | FP | TN | FN | Accuracy | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{table_rows}

Группа `manual_all` объединяет `manual_previous` и `manual_thesis`.
`template_prediction` содержит страницы, которые не получили независимую
ручную проверку.

## Сравнение F1

- F1 на всём корпусе: **{f1_all:.4f}**;
- F1 только на ручных метках: **{f1_manual:.4f}**;
- абсолютная разница: **{absolute_gap:.4f}**;
- относительное увеличение F1 при включении всего корпуса:
  **{relative_increase:.2%}**.

Автоматическая группа составляет **{template_share:.2%}** корпуса. В ней
получено FP={int(template_metrics['fp'])} и FN={int(template_metrics['fn'])}.
Нулевое число ошибок в этом срезе ожидаемо, если `has_music` было
инициализировано из `has_music_pred`, и не является независимым подтверждением
качества detector.

## Риск завышенной оценки

Метрики по всему корпусу смешивают независимые ручные метки и псевдометки,
порожденные оцениваемым detector. Это создаёт circular evaluation:

1. detector формирует `has_music_pred`;
2. прогноз переносится в `has_music`;
3. тот же прогноз сравнивается с производной от него меткой;
4. автоматически совпадающие строки увеличивают TP/TN и итоговые метрики.

В результате F1(all) характеризует не только качество классификации, но и
долю автоматически подтверждённых строк. Чем больше таких строк, тем ближе
оценка может становиться к единице независимо от качества на новых данных.

Дополнительные ограничения ручного среза:

- ручные страницы выбирались приоритетно, а не случайно;
- в `manual_thesis` намеренно представлены сложные и спорные примеры;
- страницы одного документа не отделены в независимый test split;
- часть старых ручных меток могла формироваться после просмотра прогноза.

Поэтому `manual_all` является более честной текущей оценкой, но ещё не
полностью независимым benchmark.

## Рекомендации для ВКР

1. Использовать `manual_all` как основную текущую метрику detector.
2. F1(all) приводить только как служебный показатель и явно отмечать влияние
   `template_prediction`.
3. Сформировать независимый ручной test set, стратифицированный по документам,
   типам страниц и качеству скана.
4. Выполнить document-level split: страницы одного документа не должны
   одновременно участвовать в настройке правил и финальной оценке.
5. Не использовать `has_music_pred` или `has_music_score` при присвоении
   ground truth независимой тестовой выборке.
6. Зафиксировать версию detector до разметки test set и не изменять пороги по
   результатам финального теста.
7. Приводить confusion matrix, размеры групп и доверительные интервалы вместе
   с Accuracy, Precision, Recall и F1.
8. Отдельно анализировать `music`, `mixed`, `title`, `text`, `blank`,
   `bad_scan` и `unknown`.

## Формулировка для текста ВКР

Метрики на полном корпусе нельзя интерпретировать как независимую оценку,
поскольку значительная часть меток была автоматически инициализирована
прогнозом detector. Основной текущий результат следует рассчитывать на
ручной части корпуса. Для итоговой ВКР необходим отдельный document-level
test set, размеченный без использования прогнозов оцениваемого алгоритма.
"""


def write_validation_bias_markdown(
    output_path: Path,
    report: list[dict[str, int | float | str]],
    labels_path: Path,
) -> None:
    """Save the generated validation-bias analysis."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        build_validation_bias_markdown(report, labels_path),
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
        default=Path(
            "outputs/reports/detector_metrics_by_validation_source.csv"
        ),
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        default=Path("docs/thesis/detector_validation_bias.md"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        report = write_validation_source_report(args.labels, args.out)
        write_validation_bias_markdown(
            args.markdown_out,
            report,
            args.labels,
        )
    except (FileNotFoundError, ValueError, OSError, csv.Error) as error:
        raise SystemExit(f"Error: {error}") from error

    groups = _by_group(report)
    print("Metrics by validation source:")
    for group in GROUP_ORDER:
        row = groups[group]
        print(
            f"  {group}: rows={row['rows']} "
            f"TP={row['tp']} FP={row['fp']} "
            f"TN={row['tn']} FN={row['fn']} "
            f"F1={float(row['f1']):.4f}"
        )
    f1_all = float(groups[GROUP_ALL]["f1"])
    f1_manual = float(groups[GROUP_MANUAL_ALL]["f1"])
    print(f"F1(all): {f1_all:.4f}")
    print(f"F1(manual_only): {f1_manual:.4f}")
    print(f"F1 gap: {f1_all - f1_manual:.4f}")
    print(f"CSV report: {args.out}")
    print(f"Markdown report: {args.markdown_out}")


if __name__ == "__main__":
    main()
