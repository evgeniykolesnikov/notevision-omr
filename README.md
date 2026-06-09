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

## Manual label review

Для создания локальной HTML-галереи валидированной разметки:

```bash
python scripts/build_review_gallery.py --labels data/labels/pages_validated.csv --out outputs/reports/page_review_gallery.html
```

Галерею можно отфильтровать по документу через `--doc-id`, оставить только
страницы со score от 0.1 до 0.9 через `--uncertain-only` и ограничить число
строк через `--limit N`. Изображения подключаются относительными путями, поэтому
HTML можно открыть локально в браузере.

## Preprocess music pages for OMR

Для нормализации контраста и бинаризации страниц, отмеченных
`has_music == 1`, выполните:

```bash
python scripts/preprocess_music_pages.py --labels data/labels/pages_validated.csv --out-dir outputs/preprocessed
```

Обработанные изображения сохраняются как
`outputs/preprocessed/<doc_id>/page_XXX_binary.png`, а постраничный отчёт — в
`outputs/reports/preprocessing_report.csv`. Ошибка одной страницы не
останавливает обработку остальных.

## Run Audiveris OMR

Экспериментальный запуск Audiveris CLI для одной предобработанной страницы:

```bash
python scripts/run_audiveris_omr.py --input outputs/preprocessed/rsl01004470876/page_002_binary.png --out-dir outputs/omr/rsl01004470876
```

Batch-режим обрабатывает только строки с `has_music == 1`:

```bash
python scripts/run_audiveris_omr.py --labels data/labels/pages_validated.csv --preprocessed-dir outputs/preprocessed --out-dir outputs/omr --limit 3
```

Если команда Audiveris недоступна в `PATH`, укажите путь через
`--audiveris-bin`. Stdout/stderr сохраняются в логах рядом с OMR-результатами,
а общий отчёт записывается в `outputs/reports/omr_report.csv`.

## Build OMR candidates

Для создания списка валидированных нотных страниц, подходящих для OMR:

```bash
python scripts/build_omr_candidates.py --labels data/labels/pages_validated.csv --out outputs/reports/omr_candidates.csv
```

В список попадают только строки с `has_music == 1` и `page_type == "music"`.
Колонка `preprocessed_path` указывает на ожидаемое бинарное изображение, а
`exists` показывает, создан ли файл. Доступны фильтр `--doc-id` и ограничение
`--limit N`.

## Run OMR from candidates

Рекомендуемый процесс: сначала повторно извлечь OMR-кандидатов из исходных PDF
при 300 DPI, затем передать high-resolution страницы в Audiveris:

```bash
python scripts/extract_omr_pages.py --candidates outputs/reports/omr_candidates.csv --raw-dir data/raw --out-dir outputs/omr_pages --dpi 300
python scripts/run_audiveris_omr.py --candidates outputs/reports/omr_candidates.csv --omr-pages-dir outputs/omr_pages --out-dir outputs/omr --limit 10 --audiveris-bin "C:\Program Files\Audiveris\Audiveris.exe"
```

Для thesis workflow промежуточное преобразование CSV не требуется:

```bash
python scripts/extract_omr_pages.py --candidates data/labels/omr_eval_sample_thesis.csv --raw-dir data/raw --out-dir outputs/omr_pages --dpi 300
python scripts/run_audiveris_omr.py --candidates data/labels/omr_eval_sample_thesis.csv --omr-pages-dir outputs/omr_pages --out-dir outputs/omr_300dpi --audiveris-bin "C:\Program Files\Audiveris\Audiveris.exe"
```

Поддерживаются старый формат с `exists` и `preprocessed_path`, новый thesis
формат с `image_path`, `has_music`, `page_type`, а также смешанные CSV. В
смешанной строке заполненный `preprocessed_path` сохраняет старое поведение;
иначе используется `image_path`.

При `--omr-pages-dir` вход строится как
`outputs/omr_pages/<doc_id>/page_XXX.png`; отсутствующие high-resolution файлы
получают статус `failed` без запуска Audiveris. Без этого аргумента сохраняется
старый режим: используются `preprocessed_path` и строки с `exists == True`.
Результаты каждой страницы сохраняются в `outputs/omr/<doc_id>/page_XXX/`.
Колонка `input_kind` в `omr_report.csv` показывает использованный источник.

## Extract high-resolution OMR pages

Для повторного извлечения только OMR-кандидатов из исходных PDF при 300 DPI:

```bash
python scripts/extract_omr_pages.py --candidates outputs/reports/omr_candidates.csv --raw-dir data/raw --out-dir outputs/omr_pages --dpi 300
python scripts/extract_omr_pages.py --candidates data/labels/omr_eval_sample_thesis.csv --raw-dir data/raw --out-dir outputs/omr_pages --dpi 300
```

Опция `--limit N` ограничивает число страниц для быстрой проверки. Результаты
сохраняются в `outputs/omr_pages/<doc_id>/page_XXX.png`, а отчёт — в
`outputs/reports/omr_pages_report.csv`. Каталог `outputs/pages` не изменяется:
он остаётся источником страниц основного pipeline, а `outputs/omr_pages`
используется только для Audiveris/OMR.

## Summarize OMR results

Для сводки статусов Audiveris и созданных `.mxl` файлов:

```bash
python scripts/summarize_omr_results.py --omr-report outputs/reports/omr_report.csv --omr-dir outputs/omr_300dpi --out outputs/reports/omr_summary.json
```

JSON содержит число успешных и неуспешных страниц, success rate, статистику
размеров `.mxl`, список успешных страниц с путями к результатам и список ошибок.

## Convert MXL to MIDI

Для преобразования одного результата Audiveris в MIDI:

```bash
python scripts/convert_mxl_to_midi.py --input outputs/omr_300dpi/rsl01001872102/page_013/page_013.mxl --out outputs/midi/page_013.mid
```

Пакетная конвертация рекурсивно находит все `.mxl` и сохраняет MIDI по
документам:

```bash
python scripts/convert_mxl_to_midi.py --input-dir outputs/omr_300dpi --out-dir outputs/midi --limit 10
```

При ошибках repeat-разметки конвертер сначала удаляет repeat-barline и
`RepeatExpression`, а затем при необходимости использует плоский поток
`notesAndRests`. Режим конвертации и ошибки сохраняются в
`outputs/reports/midi_conversion_report.csv`.

## Manual Review Workflow

1. Построить редактируемую статическую галерею:

   ```bash
   python scripts/build_editable_review_gallery.py --labels data/labels/pages_review_priority_thesis.csv --out outputs/reports/thesis_editable_review_gallery.html
   ```

2. Открыть HTML в браузере и разметить страницы. Изменения автоматически
   отмечаются и сохраняются в `localStorage`.
3. Экспортировать `thesis_label_corrections.csv`.
4. Применить corrections к основной thesis-разметке:

   ```bash
   python scripts/apply_label_corrections.py --labels data/labels/pages_validated_thesis.csv --corrections data/labels/thesis_label_corrections.csv --out data/labels/pages_validated_thesis.csv
   ```

5. Построить отчёт о составе и качестве документов:

   ```bash
   python scripts/build_document_quality_report.py --labels data/labels/pages_validated_thesis.csv --out outputs/reports/document_quality_report.csv
   ```

6. Построить отчёт об ошибках detector:

   ```bash
   python scripts/build_detector_error_report.py --labels data/labels/pages_validated_thesis.csv --out outputs/reports/detector_error_report.csv
   ```

7. Пересчитать итоговые метрики после применения ручных исправлений.

Подробные правила типов страниц и комментариев приведены в
`docs/thesis/labeling_guidelines.md`.

## OMR Expert Review Web App

Локальное FastAPI-приложение позволяет музыканту проверять сканы, общее аудио
и отдельные партии через защищённую паролем страницу. Оценки сохраняются в
SQLite и экспортируются в CSV, совместимый с thesis-таблицей экспертной
оценки.

Все эксперты используют общий `REVIEW_APP_PASSWORD`, но при входе обязательно
указывают своё имя. Имя нормализуется без учёта регистра и лишних пробелов:
повторный вход под тем же именем продолжает прежний прогресс. Оценки разных
музыкантов хранятся независимо.

На каждой странице достаточно выбрать пригодность результата, поставить общую
оценку от 1 до 5, отметить заметные проблемы и при необходимости оставить
комментарий. Дата завершения подставляется автоматически. Подсчёт тактов и нот
доступен в необязательном раскрывающемся блоке «Расширенная количественная
оценка».

Установка и импорт плоского пакета:

```bat
pip install -r requirements.txt
set REVIEW_APP_PASSWORD=replace-with-a-strong-password
python -m review_app.import_package --package-dir outputs/expert_review_for_send
uvicorn review_app.main:app --host 127.0.0.1 --port 8000
```

Текущая версия показывает всем экспертам один и тот же импортированный набор
из 30 страниц. Разделение выполняется на уровне прогресса и оценок. В схеме
данных зарезервировано поле `review_set`, чтобы позднее назначать разным
экспертам разные наборы без изменения модели review.

После запуска приложение доступно по адресу `http://127.0.0.1:8000`.
Экспорт находится по защищённому маршруту
`/export/expert_review.csv`.

Дополнительные переменные:

```text
REVIEW_APP_DB=review_app/review_app.db
REVIEW_PACKAGE_DIR=outputs/expert_review_for_send
```

SQLite-файл, сканы и аудио не коммитятся. Для внешнего доступа можно временно
использовать HTTPS-туннель к `127.0.0.1:8000`, но туннель следует включать
только на время согласованной экспертной проверки и выключать сразу после
сеанса. Используйте уникальный сильный пароль и не публикуйте ссылку открыто.

## Expert review metrics

После экспорта оценок из `/export/expert_review.csv` рассчитайте экспертные
метрики:

```bash
python scripts/calculate_expert_review_metrics.py --input path/to/expert_review.csv
```

Результаты сохраняются в
`outputs/reports/expert_review_metrics.csv` и
`outputs/reports/expert_review_summary.md`. Качественные метрики считаются
только по завершённым отзывам. Пустые количественные поля исключаются из
расчёта и не заменяются нулями.

Формулы:

- measure accuracy = `sum(correct_measures) / sum(checked_measures)`;
- note event error rate =
  `sum(pitch_errors + duration_errors + missing_notes + extra_notes) /
  sum(reference_notes)`;
- pitch/duration error rate используют `matched_notes` как знаменатель;
- missing/extra note rate используют `reference_notes` как знаменатель.

Техническая успешность создания MXL/MIDI `141/150` приводится в Markdown только
как отдельный контекст и не смешивается с экспертной оценкой музыкального
содержания.

## OMR failure review

Постраничный отчёт `outputs/reports/omr_failure_report.csv` можно импортировать
в тот же защищённый web-интерфейс:

```bash
python -m review_app.import_failures --report outputs/reports/omr_failure_report.csv
```

Импорт сопоставляет failure с
`outputs/pages/<doc_id>/page_XXX.png`, ищет лог в
`outputs/omr_300dpi/<doc_id>/page_XXX/` и при наличии thesis labels добавляет
`page_type`. Агрегированный `omr_pipeline_report.csv` сам по себе не содержит
номеров failed-страниц, поэтому для импорта нужен постраничный failure report.

После запуска приложения откройте `http://127.0.0.1:8000/failures`. Раздел
доступен только после входа и позволяет классифицировать причину сбоя, выбрать
решение, сохранить черновик или отметить страницу как разобранную.

Результат выгружается через `/export/failure_review.csv`. CSV совместим с
`data/labels/omr_failure_expert_review_thesis.csv` и может использоваться в ВКР
для таблицы причин OMR-сбоев, решений по повторному запуску и анализа связи
ошибок с качеством или типом страницы.

## OMR fallback at 400 DPI

400 DPI используется только как fallback-эксперимент для страниц, на которых
основной OMR при 300 DPI не создал MXL. Результаты сохраняются отдельно и не
перезаписывают `outputs/omr_300dpi` или основную метрику `141/150`.

```bat
python scripts/run_omr_fallback_dpi.py ^
  --omr-report outputs/reports/omr_pipeline_report.csv ^
  --pages-dir outputs/pages ^
  --out-dir outputs/omr_400dpi_fallback ^
  --midi-dir outputs/midi_400dpi_fallback ^
  --dpi 400 ^
  --resume ^
  --audiveris-bin "C:\Program Files\Audiveris\Audiveris.exe"
```

Агрегированный pipeline report используется для исходного размера выборки и
primary success. Номера страниц автоматически читаются из соседнего
`outputs/reports/omr_failure_report.csv`. Для честного 400 DPI исходная страница
переизвлекается из PDF в `data/raw`; масштабирование старого PNG не выполняется.

Результаты:

- `outputs/reports/omr_400dpi_fallback_report.csv`;
- `outputs/reports/omr_400dpi_fallback_summary.md`;
- MXL и логи в `outputs/omr_400dpi_fallback`;
- MIDI в `outputs/midi_400dpi_fallback`.

`fallback_recovery_rate` показывает долю fallback-попыток, восстановивших MXL.
`combined_success_rate` считается отдельно как доля исходной OMR-выборки,
успешной по полному пути MXL+MIDI после primary 300 DPI и fallback 400 DPI.
После эксперимента повторите импорт failures, чтобы статус появился в UI:

```bash
python -m review_app.import_failures --report outputs/reports/omr_failure_report.csv
```

## Данные и результаты

Реальные PDF/MRC-файлы хранятся локально в `data/raw/`, а сгенерированные
результаты — в `outputs/`. Содержимое этих каталогов не коммитится.
Файлы `.gitkeep` используются только для сохранения структуры каталогов.
