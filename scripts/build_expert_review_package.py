"""Build a self-contained review package for an external music expert."""

from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLE = (
    PROJECT_ROOT / "data" / "labels" / "omr_ground_truth_sample_thesis.csv"
)
DEFAULT_MIDI_DIR = PROJECT_ROOT / "outputs" / "midi"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "expert_review_package"

REQUIRED_COLUMNS = {"doc_id", "page_index", "image_path"}
REVIEW_COLUMNS = [
    "doc_id",
    "page_index",
    "usable",
    "pitch_quality",
    "duration_quality",
    "overall_quality",
    "comment",
]


def resolve_project_path(path_value: str, project_root: Path) -> Path:
    """Resolve a path stored in a project CSV."""
    path = Path(path_value)
    return path if path.is_absolute() else project_root / path


def build_midi_path(doc_id: str, page_index: int, midi_dir: Path) -> Path:
    """Build the expected MIDI path for one page."""
    return midi_dir / doc_id / f"page_{page_index:03d}.mid"


def build_page_directory(
    output_dir: Path,
    doc_id: str,
    page_index: int,
) -> Path:
    """Build the package directory for one reviewed page."""
    return output_dir / doc_id / f"page_{page_index:03d}"


def read_sample_rows(sample_path: Path) -> list[dict[str, str]]:
    """Read and validate the ground-truth sample CSV."""
    if not sample_path.is_file():
        raise FileNotFoundError(f"Ground-truth sample does not exist: {sample_path}")
    with sample_path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS.difference(columns)
        if missing:
            names = ", ".join(sorted(missing))
            raise ValueError(
                f"Ground-truth sample is missing required columns: {names}"
            )
        rows = list(reader)
    if not rows:
        raise ValueError(f"Ground-truth sample contains no rows: {sample_path}")
    return rows


def prepare_package_rows(
    rows: list[dict[str, str]],
    *,
    output_dir: Path,
    midi_dir: Path,
    project_root: Path,
) -> list[dict[str, object]]:
    """Resolve every input and reject incomplete or duplicate samples."""
    prepared: list[dict[str, object]] = []
    seen: set[tuple[str, int]] = set()
    missing_files: list[str] = []

    for row in rows:
        doc_id = row["doc_id"].strip()
        if not doc_id:
            raise ValueError("Ground-truth sample contains an empty doc_id.")
        try:
            page_index = int(row["page_index"])
        except ValueError as error:
            raise ValueError(
                f"Invalid page_index for {doc_id}: {row['page_index']!r}"
            ) from error
        if page_index <= 0:
            raise ValueError(
                f"page_index must be positive for {doc_id}: {page_index}"
            )

        key = (doc_id, page_index)
        if key in seen:
            raise ValueError(
                f"Duplicate page in ground-truth sample: "
                f"{doc_id}/page_{page_index:03d}"
            )
        seen.add(key)

        scan_source = resolve_project_path(row["image_path"], project_root)
        midi_source = build_midi_path(doc_id, page_index, midi_dir)
        if not scan_source.is_file():
            missing_files.append(f"scan: {scan_source}")
        if not midi_source.is_file():
            missing_files.append(f"MIDI: {midi_source}")

        page_dir = build_page_directory(output_dir, doc_id, page_index)
        prepared.append(
            {
                "doc_id": doc_id,
                "page_index": page_index,
                "scan_source": scan_source,
                "midi_source": midi_source,
                "page_dir": page_dir,
            }
        )

    if missing_files:
        preview = "\n".join(f"- {item}" for item in missing_files[:10])
        remainder = len(missing_files) - 10
        if remainder > 0:
            preview += f"\n- ... and {remainder} more"
        raise FileNotFoundError(
            "Expert package inputs are incomplete:\n" + preview
        )
    return prepared


def build_readme(page_count: int) -> str:
    """Return the Russian instruction included in the package."""
    return f"""# Пакет экспертной проверки NoteVision OMR

Пакет содержит **{page_count} страниц** для внешней музыкальной экспертизы.

## Содержимое

Для каждой страницы создан отдельный каталог:

```text
<doc_id>/page_XXX/
  scan.png
  midi.mid
```

Файл `expert_review.csv` содержит по одной строке на страницу. Заполнять нужно
только поля оценки и комментарий. `doc_id` и `page_index` изменять не следует.

## Порядок проверки

1. Откройте `scan.png` и изучите исходную нотную страницу.
2. Откройте `midi.mid` в привычном музыкальном редакторе или проигрывателе.
3. Сравните мелодию, высоты нот и ритм MIDI с исходным сканом.
4. Заполните соответствующую строку в `expert_review.csv`.
5. При заметных ошибках кратко опишите их в поле `comment`.

## Поля оценки

### `usable`

- `yes` — результат можно использовать почти без правок;
- `partial` — результат можно использовать после ручной корректировки;
- `no` — результат непригоден.

### `pitch_quality`

Оценка высоты нот от 1 до 5:

- `5` — почти без ошибок;
- `3` — есть заметные ошибки, но мелодия узнаваема;
- `1` — высоты нот в основном неверные.

### `duration_quality`

Оценка длительностей и ритма от 1 до 5:

- `5` — ритм в основном совпадает;
- `3` — есть ошибки длительностей;
- `1` — ритм существенно нарушен.

### `overall_quality`

Общая оценка от 1 до 5:

- `5` — результат пригоден для дальнейшей работы;
- `3` — результат частично пригоден;
- `1` — результат непригоден.

Промежуточные значения `2` и `4` можно использовать, если качество находится
между описанными уровнями.

### `comment`

Краткий комментарий о характерных ошибках: неверные ноты, сбитый ритм,
пропуски, лишние события, проблемы отдельных голосов или другие наблюдения.

## Важно

- Не переименовывайте каталоги и файлы.
- Не меняйте значения `doc_id` и `page_index`.
- Если MIDI не открывается, укажите `usable=no` и опишите проблему.
- Оценка должна отражать музыкальную пригодность результата, а не только факт
  успешного открытия MIDI.
"""


def write_review_csv(
    output_path: Path,
    prepared_rows: list[dict[str, object]],
) -> None:
    """Write an empty expert review template."""
    with output_path.open("w", encoding="utf-8-sig", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        for row in prepared_rows:
            writer.writerow(
                {
                    "doc_id": row["doc_id"],
                    "page_index": row["page_index"],
                    "usable": "",
                    "pitch_quality": "",
                    "duration_quality": "",
                    "overall_quality": "",
                    "comment": "",
                }
            )


def build_expert_review_package(
    sample_path: Path,
    output_dir: Path,
    *,
    midi_dir: Path = DEFAULT_MIDI_DIR,
    project_root: Path = PROJECT_ROOT,
    overwrite: bool = False,
) -> dict[str, object]:
    """Copy review artifacts and create the CSV template and README."""
    rows = read_sample_rows(sample_path)
    prepared = prepare_package_rows(
        rows,
        output_dir=output_dir,
        midi_dir=midi_dir,
        project_root=project_root,
    )

    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise FileExistsError(
            f"Output directory is not empty: {output_dir}. "
            "Use --overwrite to replace package files."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    for row in prepared:
        page_dir = Path(row["page_dir"])
        page_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(row["scan_source"]), page_dir / "scan.png")
        shutil.copy2(Path(row["midi_source"]), page_dir / "midi.mid")

    review_path = output_dir / "expert_review.csv"
    readme_path = output_dir / "README.md"
    write_review_csv(review_path, prepared)
    readme_path.write_text(build_readme(len(prepared)), encoding="utf-8")

    return {
        "pages": len(prepared),
        "scan_files": len(prepared),
        "midi_files": len(prepared),
        "review_csv": review_path,
        "readme": readme_path,
        "output_dir": output_dir,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--midi-dir", type=Path, default=DEFAULT_MIDI_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        summary = build_expert_review_package(
            args.sample,
            args.out_dir,
            midi_dir=args.midi_dir,
            overwrite=args.overwrite,
        )
    except (FileNotFoundError, FileExistsError, ValueError, OSError) as error:
        raise SystemExit(f"Error: {error}") from error

    print(f"Pages: {summary['pages']}")
    print(f"Scans copied: {summary['scan_files']}")
    print(f"MIDI copied: {summary['midi_files']}")
    print(f"Review CSV: {summary['review_csv']}")
    print(f"README: {summary['readme']}")
    print(f"Package: {summary['output_dir']}")


if __name__ == "__main__":
    main()
