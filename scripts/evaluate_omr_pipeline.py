"""Evaluate MXL and MIDI artifact coverage for the thesis OMR sample."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from typing import Iterable

REPORT_COLUMNS = [
    "doc_id",
    "sampled_pages",
    "mxl_generated_pages",
    "midi_generated_pages",
    "mxl_success_rate",
    "midi_success_rate",
]
REQUIRED_COLUMNS = {"doc_id", "page_index", "image_path"}


def _page_key(row: dict[str, str]) -> tuple[str, int]:
    doc_id = str(row.get("doc_id", "")).strip()
    try:
        page_index = int(float(str(row.get("page_index", "")).strip()))
    except ValueError as error:
        raise ValueError(
            f"Invalid page_index for document {doc_id or '<empty>'}: "
            f"{row.get('page_index', '')}"
        ) from error
    if not doc_id or page_index < 1:
        raise ValueError(
            "OMR sample contains an empty doc_id or non-positive page_index"
        )
    return doc_id, page_index


def read_omr_sample(path: Path) -> list[dict[str, str]]:
    """Read the OMR evaluation sample and validate its page identity fields."""
    if not path.is_file():
        raise FileNotFoundError(f"OMR evaluation sample does not exist: {path}")
    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        missing = sorted(REQUIRED_COLUMNS - set(reader.fieldnames or []))
        if missing:
            raise ValueError(
                "OMR evaluation sample is missing required columns: "
                + ", ".join(missing)
            )
        rows = list(reader)

    unique: dict[tuple[str, int], dict[str, str]] = {}
    for row in rows:
        unique.setdefault(_page_key(row), row)
    return [
        unique[key]
        for key in sorted(unique, key=lambda value: (value[0], value[1]))
    ]


def find_page_mxl_files(
    omr_dir: Path,
    doc_id: str,
    page_index: int,
) -> list[Path]:
    """Find every MXL export associated with one sampled page."""
    page_dir = omr_dir / doc_id / f"page_{page_index:03d}"
    return sorted(page_dir.rglob("*.mxl")) if page_dir.is_dir() else []


def find_page_midi_file(
    midi_dir: Path,
    doc_id: str,
    page_index: int,
) -> Path | None:
    """Find the canonical MIDI output associated with one sampled page."""
    document_dir = midi_dir / doc_id
    for extension in (".mid", ".midi"):
        candidate = document_dir / f"page_{page_index:03d}{extension}"
        if candidate.is_file():
            return candidate
    return None


def inspect_omr_sample_pages(
    sample_rows: Iterable[dict[str, str]],
    omr_dir: Path,
    midi_dir: Path,
) -> list[dict[str, object]]:
    """Attach MXL and MIDI availability flags to every sampled page."""
    inspected: list[dict[str, object]] = []
    seen: set[tuple[str, int]] = set()
    for row in sample_rows:
        key = _page_key(row)
        if key in seen:
            continue
        seen.add(key)
        mxl_files = find_page_mxl_files(omr_dir, key[0], key[1])
        midi_file = find_page_midi_file(midi_dir, key[0], key[1])
        inspected.append(
            {
                **row,
                "doc_id": key[0],
                "page_index": key[1],
                "has_mxl": bool(mxl_files),
                "has_midi": midi_file is not None,
            }
        )
    return sorted(
        inspected,
        key=lambda row: (str(row["doc_id"]), int(row["page_index"])),
    )


def build_omr_pipeline_rows(
    inspected_pages: Iterable[dict[str, object]],
) -> list[dict[str, object]]:
    """Aggregate sampled and generated page counts for every document."""
    documents: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for row in inspected_pages:
        documents[str(row["doc_id"])].append(row)

    report: list[dict[str, object]] = []
    for doc_id in sorted(documents):
        rows = documents[doc_id]
        sampled_pages = len(rows)
        mxl_pages = sum(bool(row["has_mxl"]) for row in rows)
        midi_pages = sum(bool(row["has_midi"]) for row in rows)
        report.append(
            {
                "doc_id": doc_id,
                "sampled_pages": sampled_pages,
                "mxl_generated_pages": mxl_pages,
                "midi_generated_pages": midi_pages,
                "mxl_success_rate": (
                    mxl_pages / sampled_pages if sampled_pages else 0.0
                ),
                "midi_success_rate": (
                    midi_pages / sampled_pages if sampled_pages else 0.0
                ),
            }
        )
    return report


def write_omr_pipeline_report(
    sample_path: Path,
    omr_dir: Path,
    midi_dir: Path,
    output_path: Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Inspect sample artifacts and save the per-document pipeline report."""
    inspected = inspect_omr_sample_pages(
        read_omr_sample(sample_path),
        omr_dir,
        midi_dir,
    )
    report = build_omr_pipeline_rows(inspected)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(report)
    return report, inspected


def build_omr_evaluation_markdown(
    inspected_pages: list[dict[str, object]],
    document_rows: list[dict[str, object]],
) -> str:
    """Generate a factual thesis report from current MXL/MIDI artifacts."""
    total = len(inspected_pages)
    mxl_pages = sum(bool(row["has_mxl"]) for row in inspected_pages)
    midi_pages = sum(bool(row["has_midi"]) for row in inspected_pages)
    missing_mxl = total - mxl_pages
    missing_midi = sum(
        bool(row["has_mxl"]) and not bool(row["has_midi"])
        for row in inspected_pages
    )
    mxl_rate = mxl_pages / total if total else 0.0
    midi_rate = midi_pages / total if total else 0.0
    problematic = sorted(
        document_rows,
        key=lambda row: (
            -(
                int(row["sampled_pages"])
                - int(row["midi_generated_pages"])
            ),
            str(row["doc_id"]),
        ),
    )[:10]
    problem_rows = "\n".join(
        f"| `{row['doc_id']}` | {row['sampled_pages']} | "
        f"{row['mxl_generated_pages']} | {row['midi_generated_pages']} | "
        f"{float(row['mxl_success_rate']):.2%} | "
        f"{float(row['midi_success_rate']):.2%} |"
        for row in problematic
    )
    if not problem_rows:
        problem_rows = "| Нет данных | 0 | 0 | 0 | 0.00% | 0.00% |"

    return f"""# Оценка OMR pipeline

Документ сформирован автоматически по выборке
`data/labels/omr_eval_sample_thesis.csv` и текущему состоянию каталогов
`outputs/omr_300dpi` и `outputs/midi`.

## Размер OMR-выборки

В оценку включено **{total} страниц** из **{len(document_rows)} документов**.
Для каждой страницы проверяется наличие хотя бы одного MXL-файла и
канонического MIDI-файла `outputs/midi/<doc_id>/page_XXX.mid`.

## Результаты

| Показатель | Значение |
|---|---:|
| Страницы с MXL | {mxl_pages} |
| Страницы с MIDI | {midi_pages} |
| Успешность OMR | {mxl_rate:.2%} |
| Успешность MIDI-конвертации | {midi_rate:.2%} |
| Страницы без MXL | {missing_mxl} |
| Страницы с MXL, но без MIDI | {missing_midi} |

Знаменателем обеих долей является полный размер OMR-выборки. Эти показатели
характеризуют наличие технических артефактов pipeline, но не музыкальную
точность содержимого MXL или MIDI.

## Проблемные документы

| doc_id | Выборка | MXL | MIDI | MXL rate | MIDI rate |
|---|---:|---:|---:|---:|---:|
{problem_rows}

Документы упорядочены по числу страниц выборки, для которых ещё не создан
MIDI. Полный документный срез хранится в
`outputs/reports/omr_pipeline_report.csv`.

## Типичные причины ошибок

На уровне файлового контроля выделяются две наблюдаемые категории:

- `missing_mxl` — для страницы не найден экспорт Audiveris; таких страниц
  **{missing_mxl}**;
- `missing_midi` — MXL найден, но MIDI для страницы отсутствует; таких страниц
  **{missing_midi}**.

Эти категории описывают место остановки pipeline, а не первопричину сбоя.
Для установления причин `missing_mxl` необходим анализ логов Audiveris,
качества скана, DPI и структуры нотного материала. Для `missing_midi`
необходимо сопоставление с отчётом конвертации music21 и ошибками repeat.

## Ограничения оценки

- Проверяется наличие файлов, а не корректность нот, длительностей, голосов и
  тактов.
- Результат зависит от текущего содержимого локальных каталогов; ещё не
  обработанная страница учитывается как отсутствие артефакта.
- Один Audiveris-запуск может создать несколько MXL для одной страницы, но в
  page-level метрике такая страница учитывается один раз.
- Для музыкальной оценки требуется экспертная ground truth и сравнение
  содержимого MXL/MIDI.
"""


def write_omr_evaluation_markdown(
    output_path: Path,
    inspected_pages: list[dict[str, object]],
    document_rows: list[dict[str, object]],
) -> None:
    """Save the generated thesis OMR evaluation chapter."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        build_omr_evaluation_markdown(inspected_pages, document_rows),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample",
        type=Path,
        default=Path("data/labels/omr_eval_sample_thesis.csv"),
    )
    parser.add_argument(
        "--omr-dir",
        type=Path,
        default=Path("outputs/omr_300dpi"),
    )
    parser.add_argument(
        "--midi-dir",
        type=Path,
        default=Path("outputs/midi"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("outputs/reports/omr_pipeline_report.csv"),
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        default=Path("docs/thesis/omr_evaluation.md"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        document_rows, inspected_pages = write_omr_pipeline_report(
            args.sample,
            args.omr_dir,
            args.midi_dir,
            args.out,
        )
        write_omr_evaluation_markdown(
            args.markdown_out,
            inspected_pages,
            document_rows,
        )
    except (FileNotFoundError, ValueError, OSError, csv.Error) as error:
        raise SystemExit(f"Error: {error}") from error

    total = len(inspected_pages)
    mxl_pages = sum(bool(row["has_mxl"]) for row in inspected_pages)
    midi_pages = sum(bool(row["has_midi"]) for row in inspected_pages)
    print(f"Sampled pages: {total}")
    print(f"MXL generated pages: {mxl_pages}")
    print(f"MIDI generated pages: {midi_pages}")
    print(f"MXL success rate: {mxl_pages / total if total else 0:.4f}")
    print(f"MIDI success rate: {midi_pages / total if total else 0:.4f}")
    print(f"Report: {args.out}")
    print(f"Thesis report: {args.markdown_out}")


if __name__ == "__main__":
    main()
