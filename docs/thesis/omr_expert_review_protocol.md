# Протокол экспертной проверки MusicXML

## Состав проверки

- успешные MXL-страницы: **30**;
- представленные документы: **14**;
- страницы `mixed`: **10**;
- страницы с `has_music_score < 0.95`: **25**;
- страницы без MXL для отдельного разбора: **9**.

Основная таблица: `data/labels/omr_expert_evaluation_thesis.csv`.  
Таблица технических сбоев: `data/labels/omr_failure_expert_review_thesis.csv`.

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
| `rsl01001872102` | 37 | `music` | `random_successful` | `outputs\omr_300dpi\rsl01001872102\page_037\page_037.mxl` |
| `rsl01001872102` | 40 | `music` | `document_coverage` | `outputs\omr_300dpi\rsl01001872102\page_040\page_040.mxl` |
| `rsl01004466011` | 47 | `music` | `document_coverage` | `outputs\omr_300dpi\rsl01004466011\page_047\page_047.mxl` |
| `rsl01004468752` | 7 | `music` | `low_confidence;document_coverage` | `outputs\omr_300dpi\rsl01004468752\page_007\page_007.mvt1.mxl` |
| `rsl01004469137` | 21 | `music` | `document_coverage` | `outputs\omr_300dpi\rsl01004469137\page_021\page_021.mxl` |
| `rsl01004469137` | 149 | `music` | `random_successful` | `outputs\omr_300dpi\rsl01004469137\page_149\page_149.mxl` |
| `rsl01004471003` | 34 | `music` | `low_confidence;document_coverage` | `outputs\omr_300dpi\rsl01004471003\page_034\page_034.mxl` |
| `rsl01004473921` | 3 | `mixed` | `mixed;low_confidence` | `outputs\omr_300dpi\rsl01004473921\page_003\page_003.mxl` |
| `rsl01004475471` | 7 | `mixed` | `mixed;failure_document;low_confidence` | `outputs\omr_300dpi\rsl01004475471\page_007\page_007.mvt1.mxl` |
| `rsl01004475471` | 9 | `mixed` | `mixed;failure_document;low_confidence` | `outputs\omr_300dpi\rsl01004475471\page_009\page_009.mvt1.mxl` |
| `rsl01010549152` | 13 | `music` | `failure_document;low_confidence` | `outputs\omr_300dpi\rsl01010549152\page_013\page_013.mxl` |
| `rsl01010549152` | 17 | `music` | `failure_document;low_confidence` | `outputs\omr_300dpi\rsl01010549152\page_017\page_017.mxl` |
| `rsl01010590489` | 14 | `mixed` | `mixed;low_confidence` | `outputs\omr_300dpi\rsl01010590489\page_014\page_014.mxl` |
| `rsl01010590489` | 21 | `mixed` | `mixed;low_confidence` | `outputs\omr_300dpi\rsl01010590489\page_021\page_021.mxl` |
| `rsl01010590489` | 25 | `music` | `low_confidence;random_successful` | `outputs\omr_300dpi\rsl01010590489\page_025\page_025.mxl` |
| `rsl01011764135` | 14 | `music` | `low_confidence;document_coverage` | `outputs\omr_300dpi\rsl01011764135\page_014\page_014.mxl` |
| `rsl01011764135` | 40 | `music` | `low_confidence;random_successful` | `outputs\omr_300dpi\rsl01011764135\page_040\page_040.mxl` |
| `rsl01012190186` | 25 | `mixed` | `mixed;failure_document;low_confidence` | `outputs\omr_300dpi\rsl01012190186\page_025\page_025.mxl` |
| `rsl01012190186` | 29 | `mixed` | `mixed;failure_document;low_confidence` | `outputs\omr_300dpi\rsl01012190186\page_029\page_029.mxl` |
| `rsl01012190186` | 37 | `mixed` | `mixed;failure_document;low_confidence;random_successful` | `outputs\omr_300dpi\rsl01012190186\page_037\page_037.mxl` |
| `rsl01012190186` | 45 | `mixed` | `mixed;failure_document;low_confidence;random_successful` | `outputs\omr_300dpi\rsl01012190186\page_045\page_045.mxl` |
| `rsl01012190186` | 49 | `mixed` | `mixed;failure_document;low_confidence` | `outputs\omr_300dpi\rsl01012190186\page_049\page_049.mxl` |
| `rsl01013682642` | 9 | `music` | `failure_document;low_confidence` | `outputs\omr_300dpi\rsl01013682642\page_009\page_009.mxl` |
| `rsl01013687437` | 17 | `music` | `failure_document;low_confidence` | `outputs\omr_300dpi\rsl01013687437\page_017\page_017.mvt1.mxl` |
| `rsl01013687437` | 28 | `music` | `failure_document;low_confidence` | `outputs\omr_300dpi\rsl01013687437\page_028\page_028.mvt1.mxl` |
| `rsl01013687437` | 31 | `music` | `failure_document;low_confidence;random_successful` | `outputs\omr_300dpi\rsl01013687437\page_031\page_031.mxl` |
| `rsl01013957967` | 8 | `music` | `low_confidence;random_successful` | `outputs\omr_300dpi\rsl01013957967\page_008\page_008.mxl` |
| `rsl01013957967` | 18 | `music` | `low_confidence;random_successful` | `outputs\omr_300dpi\rsl01013957967\page_018\page_018.mxl` |
| `rsl01013957967` | 20 | `music` | `low_confidence;random_successful` | `outputs\omr_300dpi\rsl01013957967\page_020\page_020.mxl` |
| `rsl01013957967` | 31 | `music` | `low_confidence;document_coverage` | `outputs\omr_300dpi\rsl01013957967\page_031\page_031.mxl` |

## Страницы без MXL

Для каждой страницы изучить изображение и лог Audiveris, затем заполнить
`failure_reason`, `audiveris_log_excerpt`, `image_quality_issue` и
`expert_comment`.

| doc_id | page | type | image |
|---|---:|---|---|
| `rsl01004475471` | 13 | `mixed` | `outputs\pages\rsl01004475471\page_013.png` |
| `rsl01010549152` | 6 | `music` | `outputs\pages\rsl01010549152\page_006.png` |
| `rsl01012190186` | 33 | `mixed` | `outputs\pages\rsl01012190186\page_033.png` |
| `rsl01012190186` | 53 | `mixed` | `outputs\pages\rsl01012190186\page_053.png` |
| `rsl01013682642` | 12 | `music` | `outputs\pages\rsl01013682642\page_012.png` |
| `rsl01013682642` | 13 | `music` | `outputs\pages\rsl01013682642\page_013.png` |
| `rsl01013687437` | 18 | `music` | `outputs\pages\rsl01013687437\page_018.png` |
| `rsl01013687437` | 19 | `music` | `outputs\pages\rsl01013687437\page_019.png` |
| `rsl01013687437` | 21 | `music` | `outputs\pages\rsl01013687437\page_021.png` |

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
