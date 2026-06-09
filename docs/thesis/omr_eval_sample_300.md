# Расширенная OMR-выборка на 300 страниц

## Цель

Выборка предназначена для следующего технического эксперимента Audiveris после
первичной оценки на 150 страницах. Она увеличивает охват документов и отдельно
включает известные сложные случаи. Результат нового запуска нельзя механически
объединять с метрикой `141/150`: дизайн выборок различается.

## Сборка

```powershell
python scripts/build_omr_eval_sample.py `
  --labels data/labels/pages_validated_thesis.csv `
  --pages-dir outputs/pages `
  --out data/labels/omr_eval_sample_300_thesis.csv `
  --summary outputs/reports/omr_eval_sample_300_summary.md `
  --sample-size 300 `
  --random-seed 42
```

Builder объединяет ручные labels, доступные предсказания CNN и Random Forest,
предыдущие OMR failures и fallback-отчёты по ключу `doc_id + page_index`.
Страница включается только при наличии PNG в `outputs/pages`.

## Приоритеты

1. Предыдущие OMR failures.
2. Страницы, восстановленные fallback-экспериментами.
3. Расхождения CNN и Random Forest.
4. Страницы `mixed`.
5. Кандидаты с classifier confidence ниже `0.95`.
6. Случайные оставшиеся музыкальные кандидаты.

Если у страницы несколько причин, все они сохраняются в `source_reason`, а
`sample_group` получает наиболее высокий приоритет. Дубликаты удаляются по
`doc_id + page_index`.

## Текущая сборка

При seed `42` сформировано 300 страниц из 2262 доступных кандидатов:

- 39 документов;
- 9 предыдущих OMR failures;
- 43 model disagreements;
- 24 страницы `mixed` в итоговой выборке;
- все 300 путей к изображениям существуют.

Два preprocessing-recovered случая присутствуют в `source_reason`; их основной
`sample_group` остаётся `previous_omr_failure`, поскольку эта причина имеет
более высокий приоритет.

## Запуск эксперимента

```powershell
python scripts/extract_omr_pages.py --candidates data/labels/omr_eval_sample_300_thesis.csv --raw-dir data/raw --out-dir outputs/omr_pages_300_sample --dpi 300

python scripts/run_audiveris_omr.py --candidates data/labels/omr_eval_sample_300_thesis.csv --omr-pages-dir outputs/omr_pages_300_sample --out-dir outputs/omr_300dpi_sample --audiveris-bin "C:\Program Files\Audiveris\Audiveris.exe" --resume --skip-existing
```

После Audiveris необходимо отдельно построить MXL/MIDI report и failure
analysis для этой выборки.

## Ограничения

- Выборка специально обогащена сложными страницами и не является простой
  случайной выборкой корпуса.
- Предсказание classifier не считается ground truth.
- Наличие MXL/MIDI измеряет technical success, но не музыкальную корректность.
- Не все документы без PDF или извлечённых PNG могут участвовать в выборке.
