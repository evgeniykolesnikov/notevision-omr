"""Initialize thesis MusicXML expert-review tables and review protocol."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from build_omr_ground_truth_sample import (
    find_page_mxl,
    read_omr_eval_sample,
)

EXPERT_COLUMNS = [
    "doc_id",
    "page_index",
    "page_type",
    "image_path",
    "has_music_score",
    "selection_reason",
    "mxl_path",
    "reviewer",
    "review_date",
    "checked_measures",
    "correct_measures",
    "reference_notes",
    "matched_notes",
    "pitch_errors",
    "duration_errors",
    "missing_notes",
    "extra_notes",
    "voice_errors",
    "measure_errors",
    "page_usable",
    "dominant_error",
    "expert_comment",
]
EXPERT_REQUIRED_INPUT = {
    "doc_id",
    "page_index",
    "page_type",
    "image_path",
    "has_music_score",
    "selection_reason",
    "mxl_path",
}

FAILURE_COLUMNS = [
    "doc_id",
    "page_index",
    "page_type",
    "image_path",
    "failure_reason",
    "audiveris_log_excerpt",
    "image_quality_issue",
    "expert_comment",
]


def _page_key(row: dict[str, str]) -> tuple[str, int]:
    doc_id = str(row.get("doc_id", "")).strip()
    try:
        page_index = int(float(str(row.get("page_index", "")).strip()))
    except ValueError as error:
        raise ValueError(
            f"Invalid page_index for {doc_id or '<missing>'}: "
            f"{row.get('page_index', '')}"
        ) from error
    return doc_id, page_index


def read_ground_truth_sample(path: Path) -> list[dict[str, str]]:
    """Read the selected expert pages and validate their required fields."""
    if not path.is_file():
        raise FileNotFoundError(f"Ground-truth sample does not exist: {path}")
    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        missing = sorted(
            EXPERT_REQUIRED_INPUT - set(reader.fieldnames or [])
        )
        if missing:
            raise ValueError(
                "Ground-truth sample is missing required columns: "
                + ", ".join(missing)
            )
        return list(reader)


def build_expert_review_rows(
    sample_rows: list[dict[str, str]],
) -> list[dict[str, object]]:
    """Create empty expert-review fields after checking each MXL file."""
    rows: list[dict[str, object]] = []
    for source in sample_rows:
        mxl_path = Path(str(source["mxl_path"]))
        if not mxl_path.is_file():
            key = _page_key(source)
            raise FileNotFoundError(
                f"MXL file does not exist for {key[0]}/page_{key[1]}: "
                f"{mxl_path}"
            )
        row = {column: "" for column in EXPERT_COLUMNS}
        for column in EXPERT_REQUIRED_INPUT:
            row[column] = source.get(column, "")
        row["page_index"] = _page_key(source)[1]
        rows.append(row)
    return sorted(
        rows,
        key=lambda row: (str(row["doc_id"]), int(row["page_index"])),
    )


def build_failure_review_rows(
    omr_rows: list[dict[str, str]],
    omr_dir: Path,
) -> list[dict[str, object]]:
    """Create review rows for every fixed-sample page without an MXL file."""
    if not omr_dir.is_dir():
        raise FileNotFoundError(f"OMR directory does not exist: {omr_dir}")
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, int]] = set()
    for source in omr_rows:
        key = _page_key(source)
        if key in seen:
            continue
        seen.add(key)
        if find_page_mxl(omr_dir, key[0], key[1]) is not None:
            continue
        rows.append(
            {
                "doc_id": key[0],
                "page_index": key[1],
                "page_type": source.get("page_type", ""),
                "image_path": source.get("image_path", ""),
                "failure_reason": "",
                "audiveris_log_excerpt": "",
                "image_quality_issue": "",
                "expert_comment": "",
            }
        )
    return sorted(
        rows,
        key=lambda row: (str(row["doc_id"]), int(row["page_index"])),
    )


def _write_csv(
    path: Path,
    columns: list[str],
    rows: list[dict[str, object]],
    *,
    overwrite: bool,
) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(
            f"Output already exists: {path}. Pass --overwrite to replace it."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def build_expert_review_protocol(
    expert_rows: list[dict[str, object]],
    failure_rows: list[dict[str, object]],
    expert_path: Path,
    failure_path: Path,
) -> str:
    """Create the practical annotation protocol for the selected pages."""
    documents = len({str(row["doc_id"]) for row in expert_rows})
    mixed = sum(row["page_type"] == "mixed" for row in expert_rows)
    low_confidence = sum(
        float(str(row["has_music_score"])) < 0.95 for row in expert_rows
    )
    page_table = "\n".join(
        f"| `{row['doc_id']}` | {int(row['page_index'])} | "
        f"`{row['page_type']}` | `{row['selection_reason']}` | "
        f"`{row['mxl_path']}` |"
        for row in expert_rows
    )
    failure_table = "\n".join(
        f"| `{row['doc_id']}` | {int(row['page_index'])} | "
        f"`{row['page_type']}` | `{row['image_path']}` |"
        for row in failure_rows
    )
    if not failure_table:
        failure_table = "| Нет failures | - | - | - |"

    return f"""# Протокол экспертной проверки MusicXML

## Состав проверки

- успешные MXL-страницы: **{len(expert_rows)}**;
- представленные документы: **{documents}**;
- страницы `mixed`: **{mixed}**;
- страницы с `has_music_score < 0.95`: **{low_confidence}**;
- страницы без MXL для отдельного разбора: **{len(failure_rows)}**.

Основная таблица: `{expert_path.as_posix()}`.  
Таблица технических сбоев: `{failure_path.as_posix()}`.

## Подготовка

1. Открыть исходное изображение из `image_path`.
2. Открыть соответствующий `mxl_path` в MuseScore.
3. Не исправлять MXL до завершения подсчёта ошибок.
4. Для длинной страницы проверить первые 5 полных тактов и 5 тактов из
   середины. Для короткой страницы проверить все доступные такты.
5. Использовать одинаковое правило выбора фрагментов на всех страницах.

## Заполнение основной таблицы

Для каждой страницы заполнить:

- `reviewer`, `review_date`;
- `checked_measures`, `correct_measures`;
- `reference_notes`, `matched_notes`;
- `pitch_errors`, `duration_errors`;
- `missing_notes`, `extra_notes`;
- `voice_errors`, `measure_errors`;
- `page_usable`: `yes`, `partial` или `no`;
- `dominant_error` и `expert_comment`.

Все счётчики должны быть целыми неотрицательными числами. `matched_notes` не
может превышать `reference_notes`, а `correct_measures` —
`checked_measures`.

## Правила подсчёта

- `pitch_errors`: сопоставленная нота имеет неверную высоту или октаву;
- `duration_errors`: неверная длительность ноты или паузы;
- `missing_notes`: нота исходника отсутствует в MusicXML;
- `extra_notes`: MusicXML содержит отсутствующую в исходнике ноту;
- `voice_errors`: событие отнесено к неверному голосу либо голоса ошибочно
  объединены или разделены;
- `measure_errors`: пропуск, добавление или нарушение структуры такта,
  тактовой черты, размера, затакта или повтора.

## Проверка качества разметки

После основной проверки повторно оценить не менее 6 страниц без просмотра
первоначальных значений. При наличии второго эксперта передать ему те же
страницы. Расхождения зафиксировать в `expert_comment`.

## Выбранные MXL-страницы

| doc_id | page | type | selection reason | MXL |
|---|---:|---|---|---|
{page_table}

## Страницы без MXL

Для каждой страницы изучить изображение и лог Audiveris, затем заполнить
`failure_reason`, `audiveris_log_excerpt`, `image_quality_issue` и
`expert_comment`.

| doc_id | page | type | image |
|---|---:|---|---|
{failure_table}

## Итоговые показатели

После заполнения таблиц рассчитать:

- page usability rate;
- measure accuracy;
- note event error rate;
- pitch и duration error rates;
- missing и extra note rates;
- voice и measure error rates;
- micro- и macro-average.

Технический результат `141/150 = 94%` приводится отдельно. Экспертные метрики
характеризуют качество только проверенной стратифицированной подвыборки и не
должны называться точностью всех 141 MXL без дополнительного обоснования.
"""


def initialize_omr_expert_review(
    ground_truth_sample_path: Path,
    omr_eval_sample_path: Path,
    omr_dir: Path,
    expert_output_path: Path,
    failure_output_path: Path,
    protocol_output_path: Path,
    *,
    overwrite: bool = False,
) -> dict[str, int]:
    """Validate inputs and initialize both review tables and the protocol."""
    expert_rows = build_expert_review_rows(
        read_ground_truth_sample(ground_truth_sample_path)
    )
    _, omr_rows = read_omr_eval_sample(omr_eval_sample_path)
    failure_rows = build_failure_review_rows(omr_rows, omr_dir)

    for path in (expert_output_path, failure_output_path, protocol_output_path):
        if path.exists() and not overwrite:
            raise FileExistsError(
                f"Output already exists: {path}. Pass --overwrite to replace it."
            )

    _write_csv(
        expert_output_path,
        EXPERT_COLUMNS,
        expert_rows,
        overwrite=True,
    )
    _write_csv(
        failure_output_path,
        FAILURE_COLUMNS,
        failure_rows,
        overwrite=True,
    )
    protocol_output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_protocol = protocol_output_path.with_suffix(
        protocol_output_path.suffix + ".tmp"
    )
    temporary_protocol.write_text(
        build_expert_review_protocol(
            expert_rows,
            failure_rows,
            expert_output_path,
            failure_output_path,
        ),
        encoding="utf-8",
    )
    temporary_protocol.replace(protocol_output_path)
    return {
        "expert_pages": len(expert_rows),
        "failure_pages": len(failure_rows),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ground-truth-sample",
        type=Path,
        default=Path("data/labels/omr_ground_truth_sample_thesis.csv"),
    )
    parser.add_argument(
        "--omr-sample",
        type=Path,
        default=Path("data/labels/omr_eval_sample_thesis.csv"),
    )
    parser.add_argument(
        "--omr-dir",
        type=Path,
        default=Path("outputs/omr_300dpi"),
    )
    parser.add_argument(
        "--expert-out",
        type=Path,
        default=Path("data/labels/omr_expert_evaluation_thesis.csv"),
    )
    parser.add_argument(
        "--failure-out",
        type=Path,
        default=Path("data/labels/omr_failure_expert_review_thesis.csv"),
    )
    parser.add_argument(
        "--protocol-out",
        type=Path,
        default=Path("docs/thesis/omr_expert_review_protocol.md"),
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        summary = initialize_omr_expert_review(
            args.ground_truth_sample,
            args.omr_sample,
            args.omr_dir,
            args.expert_out,
            args.failure_out,
            args.protocol_out,
            overwrite=args.overwrite,
        )
    except (
        FileExistsError,
        FileNotFoundError,
        ValueError,
        OSError,
        csv.Error,
    ) as error:
        raise SystemExit(f"Error: {error}") from error

    print(f"Expert review pages: {summary['expert_pages']}")
    print(f"Failure review pages: {summary['failure_pages']}")
    print(f"Expert CSV: {args.expert_out}")
    print(f"Failure CSV: {args.failure_out}")
    print(f"Protocol: {args.protocol_out}")


if __name__ == "__main__":
    main()
