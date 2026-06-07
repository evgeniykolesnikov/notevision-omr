# notevision-omr

Система анализа сканированных нотных документов.

## Цель

`PDF/MRC -> страницы -> выявление нотных страниц -> OMR -> MusicXML/MIDI -> музыкальные признаки`

## Структура проекта

```text
data/           исходные данные, разметка и промежуточные наборы
docs/           постановка задачи, требования, план данных и архитектура
notebooks/      исследовательские ноутбуки и эксперименты
src/notevision/ основной Python-пакет
scripts/        команды запуска этапов конвейера
outputs/        сгенерированные страницы, прогнозы, OMR и отчёты
tests/          автоматические тесты
```

Модули пакета отвечают за извлечение страниц из PDF, разбор MRC, подготовку
изображений, классификацию страниц, OMR, экспорт MusicXML/MIDI, вычисление
метрик и интерфейс Streamlit.

## Установка

Требуется Python 3.10 или новее.

```bash
python -m venv .venv
```

Активация окружения в PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Установка зависимостей:

```bash
python -m pip install -r requirements.txt
```

При необходимости скопируйте `.env.example` в `.env` и измените пути.

## Import downloaded RSL files

Скачанные PDF и MRC можно складывать без переименования в общую папку
`data/inbox/`. Скрипт сопоставит файлы по идентификатору РГБ, создаст папки
`data/raw/<doc_id>/`, скопирует туда исходные файлы и добавит `source.txt`:

```bash
python scripts/organize_raw_files.py --inbox data/inbox --raw-dir data/raw
```

По умолчанию файлы копируются. Флаг `--move` перемещает их, а `--overwrite`
разрешает замену уже существующих файлов. Отчёт сохраняется в
`outputs/reports/raw_import_report.csv`.

После импорта остальные этапы pipeline запускаются для папки
`data/raw/<doc_id>/`, например через аргумент `--document-dir`.

## Extract PDF pages

Исходные PDF хранятся локально в `data/raw/` и не коммитятся в репозиторий.
Рекомендуемый вариант: передать папку документа. Скрипт сам найдёт единственный
PDF внутри неё, поэтому переименовывать файл в `document.pdf` не требуется:

```bash
python scripts/extract_pages.py --document-dir data/raw/rsl01004470876 --out outputs/pages/rsl01004470876 --dpi 200
```

Также можно явно передать путь к PDF:

```bash
python scripts/extract_pages.py --pdf data/raw/rsl01004470876/rsl01004470876.pdf --out outputs/pages/rsl01004470876 --doc-id rsl01004470876 --dpi 200
```

Изображения будут названы `page_001.png`, `page_002.png` и далее.

## Parse MRC metadata

MRC-файл хранится локально в папке `data/raw/<doc_id>/` рядом с PDF и не
коммитится в репозиторий. Чтобы найти единственный MRC в папке документа,
распарсить метаданные и сохранить JSON, выполните:

```bash
python scripts/parse_mrc.py --document-dir data/raw/rsl01004470876 --out outputs/reports/rsl01004470876_metadata.json
```

Для обработки всех папок документов и создания общего CSV:

```bash
python scripts/parse_mrc_batch.py --raw-dir data/raw --out outputs/reports/all_metadata.csv
```

Ошибки отдельных документов сохраняются в
`outputs/reports/mrc_parse_errors.csv` и не останавливают пакетную обработку.

## Detect music pages

Baseline-классификатор выделяет горизонтальные линии на изображениях страниц,
оценивает группы нотных станов и сохраняет rule-based прогнозы в CSV:

```bash
python scripts/run_pipeline.py --manifest outputs/pages/rsl01004470876/manifest.csv --out outputs/predictions/rsl01004470876_page_predictions.csv
```

## Evaluate music page detection

Для сравнения прогнозов с ручной разметкой и расчёта accuracy, precision,
recall, F1 и confusion matrix выполните:

```bash
python scripts/evaluate.py --labels data/labels/pages.csv --predictions outputs/predictions/rsl01004470876_page_predictions.csv --out outputs/reports/rsl01004470876_metrics.json
```

Если разметка содержит колонку `page_type`, JSON также включает краткую
сводку ошибок для каждого типа страниц.

## Evaluate batch predictions

Для оценки валидированной разметки по всем файлам прогнозов:

```bash
python scripts/evaluate_batch.py --labels data/labels/pages_validated.csv --predictions-dir outputs/predictions --out outputs/reports/validated_metrics.json
```

JSON содержит общие метрики, confusion matrix и метрики по каждому `doc_id`.
При наличии `page_type` также добавляется сводка ошибок по типам страниц.
Лишние строки прогнозов игнорируются, но для каждой размеченной страницы
предсказание обязательно.

## Batch processing

Для обработки всех папок `data/raw/<doc_id>/` одной командой выполните:

```bash
python scripts/batch_run_pipeline.py --raw-dir data/raw --outputs-dir outputs --dpi 200
```

Batch pipeline извлекает страницы, сохраняет MRC-метаданные при их наличии,
определяет страницы с нотной записью и формирует общий отчёт
`outputs/reports/batch_pipeline_report.csv`. Все прогнозы страниц объединяются
в `outputs/reports/all_page_predictions.csv`. Ошибка одного документа не
останавливает обработку остальных.

## Build labels template

Для создания CSV-шаблона ручной разметки на основе общего файла прогнозов:

```bash
python scripts/build_labels_template.py --predictions outputs/reports/all_page_predictions.csv --out data/labels/pages_template.csv
```

Значения `has_music` и `page_type` предварительно заполняются из baseline-
прогноза. Флаг `--sample-only N` оставляет первые N страниц каждого документа
для быстрой проверки, а `--overwrite` разрешает заменить существующий шаблон.

## Данные и результаты

Реальные PDF/MRC-файлы хранятся локально в `data/raw/`, а сгенерированные
результаты — в `outputs/`. Содержимое этих каталогов не коммитится.
Файлы `.gitkeep` используются только для сохранения структуры каталогов.
