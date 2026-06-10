# Оркестрация OMR evaluation pipeline

## Назначение

Первоначальные OMR-эксперименты выполнялись последовательным ручным запуском
нескольких скриптов. Такой режим полезен для исследования отдельных этапов,
но неудобен для воспроизводимого MVP: можно пропустить MIDI conversion,
перезапустить уже готовый Audiveris result или смешать primary и fallback
метрики.

`scripts/run_omr_eval_pipeline.py` объединяет существующие компоненты без
замены их внутренней логики.

## Запуск

```powershell
python scripts/run_omr_eval_pipeline.py `
  --sample data/labels/omr_eval_sample_300_thesis.csv `
  --pages-dir outputs/pages `
  --raw-dir data/raw `
  --out-root outputs/omr_eval_300_pipeline `
  --reports-dir outputs/reports `
  --audiveris-bin "C:\Program Files\Audiveris\Audiveris.exe" `
  --resume
```

`--limit N` ограничивает число первых страниц выборки и предназначен для
короткой проверки конфигурации.

## Последовательность

1. Из sample CSV читаются уникальные `doc_id + page_index`.
2. Страницы повторно извлекаются из исходных PDF при 300 DPI.
3. Audiveris запускается для primary OMR.
4. Каждый найденный MXL сразу конвертируется в MIDI.
5. Формируется page-level primary evaluation.
6. Страницы без MXL повторно извлекаются и обрабатываются при 400 DPI.
7. Восстановленные MXL конвертируются в отдельный fallback MIDI-каталог.
8. Для оставшихся failures запускаются варианты crop/deskew/CLAHE/threshold.
9. Primary и fallback artifacts объединяются в финальный page-level report.

## Структура результатов

Внутри `--out-root` используются независимые каталоги:

```text
primary_pages_300dpi/
primary_omr/
primary_midi/
fallback_400dpi_omr/
fallback_400dpi_midi/
preprocessing_omr/
preprocessing_midi/
```

Это не позволяет fallback-результатам перезаписать primary artifacts и
сохраняет возможность отдельно пересчитать метрики каждого этапа.

Имена отчётов получают prefix из имени `--out-root`:

```text
<prefix>_primary_report.csv
<prefix>_primary_failures.csv
<prefix>_fallback_400dpi.csv
<prefix>_preprocessing_fallback.csv
<prefix>_combined_report.csv
<prefix>_summary.md
```

## Resume

При `--resume`:

- существующий primary PNG при 300 DPI не извлекается повторно;
- Audiveris не запускается, если MXL уже существует;
- MIDI не конвертируется повторно, если canonical `.mid` уже существует;
- 400 DPI и preprocessing fallback используют собственную skip/resume логику.

Ошибка одной страницы сохраняется в соответствующем stage report и не должна
останавливать обработку остальных страниц. Повторный запуск с `--resume`
продолжает незавершённые страницы.

## Метрики

Summary раздельно показывает:

- primary MXL/MIDI pages и success rates;
- число попыток и recovery при 400 DPI;
- число preprocessing attempts и recovered pages;
- final combined MXL/MIDI pages и success rates;
- страницы, оставшиеся без MXL.

Primary success не пересчитывается после fallback. Combined success является
отдельной метрикой технической доступности артефактов.

## Ограничение интерпретации

Наличие MXL или MIDI означает только технический success соответствующего
этапа. Orchestrator не проверяет правильность нот, длительностей, голосов,
тактов и повторов. Musical correctness оценивается отдельно экспертами по
исходному скану.

## Исследовательский режим

Отдельные скрипты сохраняются и остаются предпочтительными, когда требуется:

- проверить один DPI;
- запустить один preprocessing variant;
- повторить только MIDI conversion;
- исследовать конкретную failed page;
- измерить runtime отдельного этапа.

Orchestrator является рекомендуемым способом полного воспроизводимого запуска
MVP, но не заменяет эти диагностические инструменты.
