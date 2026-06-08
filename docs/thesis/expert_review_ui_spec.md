# Архитектура экспертного web-интерфейса NoteVision OMR

## Назначение

Интерфейс предназначен для двух связанных видов проверки:

1. оператор подтверждает или исправляет результат detector на уровне страницы;
2. музыкальный эксперт оценивает техническую и содержательную пригодность результата OMR.

Web-интерфейс не должен запускать Audiveris внутри HTTP-запроса. Длительные операции передаются в очередь, а пользователь работает с сохранённым состоянием задачи. CSV остаётся форматом обмена с исследовательскими скриптами ВКР, но основным источником актуального состояния становится база данных.

Целевой поток:

```text
PDF/MRC
→ detector
→ проверка типа страницы
→ OMR queue
→ Audiveris/MXL
→ MIDI
→ экспертная проверка
→ версионированная оценка
→ автоматический CSV/JSON-экспорт
```

## 1. Экран проверки detector

### Назначение

Экран используется оператором для подтверждения или исправления:

- `page_type`;
- `has_music`;
- `quality_comment`;
- тегов качества;
- необходимости OMR;
- признака возможного дубликата.

### Основные элементы

- фильтры по документу, статусу проверки, `page_type`, confidence и тегам;
- сортировка по `has_music_score`, номеру страницы и приоритету;
- изображение страницы с масштабированием;
- соседние страницы документа для контекста;
- исходный прогноз `has_music_pred` и `has_music_score`;
- текущая валидированная метка;
- быстрые кнопки `Music`, `Mixed`, `Title`, `Text`, `Blank`, `Bad scan`;
- теги `photo_scan`, `handwritten_notation`, `handwritten_text`, `color_patch`, `bleed_through`, `duplicate_candidate`;
- комментарий оператора;
- действия `Save`, `Save and next`, `Skip`, `Return to queue`;
- индикатор несохранённых изменений;
- история предыдущих исправлений.

`unknown` используется только при невозможности принять решение. Для `music` и `mixed` значение `has_music` автоматически устанавливается в `1`; для `title`, `text`, `blank` и `bad_scan` — в `0`, но оператор видит итоговое значение до сохранения.

### Фильтры очереди

- `needs_review = true`;
- confidence от 0.1 до 0.9;
- расхождение между prediction и validation;
- только страницы определённого документа;
- boundary pages;
- только `unknown`;
- только специальные теги;
- только ранее не проверенные страницы;
- страницы, возвращённые экспертом после OMR.

### ASCII-wireframe

```text
+--------------------------------------------------------------------------------+
| NoteVision | Detector review | Document [All v] | Status [Needs review v]      |
| Score [0.10 ---- 0.90] | Type [All v] | Tag [All v] | Sort [Score asc v]      |
+--------------------------------------------------------------------------------+
| Queue: 128 pages                  rsl01013687437 / page 018            37 / 128 |
+---------------------------+----------------------------------------------------+
|                           | Prediction                                          |
|                           | has_music_pred: 1    score: 0.72                    |
|       PAGE IMAGE          |                                                    |
|      [ - ] [100%] [ + ]   | Validated label                                    |
|                           | page_type [ music v ]   has_music [ 1 v ]           |
|                           |                                                    |
|                           | [Music] [Mixed] [Title] [Text] [Blank] [Bad scan]  |
|                           |                                                    |
|                           | Tags: [x] photo_scan  [ ] handwritten_notation     |
|                           |       [ ] color_patch [ ] bleed_through            |
|                           |       [ ] duplicate_candidate                      |
|                           |                                                    |
|                           | Quality comment                                    |
|                           | +------------------------------------------------+ |
|                           | |                                                | |
|                           | +------------------------------------------------+ |
+---------------------------+----------------------------------------------------+
| [Previous page] [Skip] [Save] [Save and next]       History [3 changes v]     |
+--------------------------------------------------------------------------------+
```

### Результат сохранения

После подтверждения:

- создаётся новая версия ручной метки;
- `validation_source` получает значение `manual_thesis` либо более общее `manual_operator`;
- `needs_review` становится `false`, если оператор принял окончательное решение;
- сохраняются пользователь, время, исходные и новые значения;
- для `music`/`mixed` может быть создана задача `extract_omr_page`;
- автоматически обновляется приоритет очереди следующих этапов.

## 2. Экран проверки OMR

### Назначение

Экран показывает результат выполнения Audiveris и позволяет разобрать:

- успешные MXL;
- страницы без MXL;
- отсутствие MIDI;
- ошибки запуска и повторные попытки;
- страницы, технически обработанные, но непригодные для экспертной проверки.

### Основные элементы

- статус `queued`, `running`, `succeeded`, `failed`, `cancelled`;
- число попыток и время обработки;
- версия Audiveris и параметры запуска;
- путь и checksum входного изображения;
- наличие MXL и MIDI;
- краткий фрагмент `stdout`/`stderr`;
- категория ошибки;
- кнопки `Retry`, `Retry with parameters`, `Mark as non-OMR`, `Send to operator`;
- ссылка на экран scan + MXL + MIDI при успешном результате;
- фильтры по документу, failure reason, числу попыток и времени выполнения.

Категории технических ошибок:

- `missing_mxl`;
- `missing_midi`;
- `small_interline`;
- `invalid_image`;
- `timeout`;
- `audiveris_process_error`;
- `musicxml_parse_error`;
- `midi_conversion_error`;
- `unknown_failure`.

### ASCII-wireframe

```text
+--------------------------------------------------------------------------------+
| OMR jobs | Status [Failed v] | Document [All v] | Error [All v] | Retry [All] |
+--------------------------------------------------------------------------------+
| Page                 | Status | MXL | MIDI | Attempts | Time   | Failure        |
| rsl...75471 / 013    | failed | no  | no   | 2        | 03:41  | small_interline|
| rsl...549152 / 006   | failed | no  | no   | 1        | 01:58  | process_error  |
+--------------------------------------------------------------------------------+
| Selected: rsl01004475471 / page 013                                            |
+-----------------------------+--------------------------------------------------+
|                             | Job ID: 7d64...                                  |
|       PAGE IMAGE            | Audiveris: <version>   DPI: 300                 |
|                             | Started: ...          Finished: ...             |
|                             | Command/config: [view]                           |
|                             |                                                  |
|                             | Log excerpt                                      |
|                             | +----------------------------------------------+ |
|                             | | Interline value ...                          | |
|                             | +----------------------------------------------+ |
+-----------------------------+--------------------------------------------------+
| [Retry] [Retry with parameters] [Send to operator] [Mark as reviewed failure] |
+--------------------------------------------------------------------------------+
```

### Разбор failure

Для страниц без MXL эксперт или разработчик заполняет:

- `failure_reason`;
- `audiveris_log_excerpt`;
- `image_quality_issue`;
- `expert_comment`;
- решение `retry`, `exclude`, `requires_preprocessing` или `requires_manual_entry`.

Эти поля соответствуют `data/labels/omr_failure_expert_review_thesis.csv`.

## 3. Экран scan + MXL + MIDI

### Назначение

Это основной экран музыкального эксперта. Он должен явно разделять:

- технический успех создания файлов;
- структурную пригодность MusicXML;
- музыкальную корректность;
- практическую пригодность результата.

### Компоновка

- слева — исходный скан;
- справа — MusicXML, отрисованный в браузере;
- снизу — MIDI playback и форма экспертной оценки;
- сверху — данные документа, навигация и статус сохранения.

### Возможности просмотра

- независимое масштабирование скана и партитуры;
- поворот и коррекция отображения скана без изменения исходного файла;
- переход между страницами документа;
- полноэкранный режим каждой панели;
- отображение номера системы или такта, если он доступен в MusicXML;
- маркеры проверяемых тактов;
- ссылка на скачивание исходного MXL и MIDI;
- отображение версии OMR-результата.

### MIDI playback

Минимальный вариант:

- загрузка существующего `.mid`;
- воспроизведение в браузере через JavaScript MIDI parser и Web Audio;
- piano/soundfont по умолчанию;
- play, pause, stop, seek, tempo и volume;
- подсветка текущего такта как последующее улучшение.

Web MIDI API не следует делать обязательным: он ориентирован на доступ к MIDI-устройствам и имеет ограничения совместимости и разрешений. Для воспроизводимой экспертной проверки достаточно browser playback через Web Audio или предварительно созданного аудиофайла.

### Форма экспертной оценки

- `reviewer`;
- `review_date`;
- `checked_measures`;
- `correct_measures`;
- `reference_notes`;
- `matched_notes`;
- `pitch_errors`;
- `duration_errors`;
- `missing_notes`;
- `extra_notes`;
- `voice_errors`;
- `measure_errors`;
- `page_usable`: `yes`, `partial`, `no`;
- `dominant_error`;
- `expert_comment`;
- `requires_new_omr`;
- версия протокола оценки.

Валидация формы:

- счётчики — целые неотрицательные числа;
- `correct_measures <= checked_measures`;
- `matched_notes <= reference_notes`;
- при `page_usable=no` требуется `dominant_error` или комментарий;
- завершённая оценка должна содержать имя эксперта и дату;
- автосохранённый черновик не считается завершённой оценкой.

### ASCII-wireframe

```text
+--------------------------------------------------------------------------------+
| rsl01012190186 / page 037 | OMR v3 | Review: draft | [Prev] [Next] [Save]      |
+---------------------------------------+----------------------------------------+
| SOURCE SCAN                           | RENDERED MUSICXML                      |
| [Rotate] [Fit] [-] 100% [+]           | [Fit width] [-] 90% [+]               |
|                                       |                                        |
|          scanned page                 |          rendered score                |
|                                       |                                        |
|                                       |                                        |
+---------------------------------------+----------------------------------------+
| MIDI: [Play] [Pause] [Stop] |------o--------------| Tempo [100%] Volume [80%] |
| Sound: [Piano v]                 [Download MXL] [Download MIDI]                 |
+--------------------------------------------------------------------------------+
| Checked measures [ 10 ]  Correct [ 8 ] | Reference notes [120] Matched [112]  |
| Pitch [3] Duration [4] Missing [8] Extra [2] Voice [1] Measure [2]            |
| Usable: ( ) yes  (x) partial  ( ) no   Dominant error [missing_notes v]       |
| Comment                                                                        |
| +----------------------------------------------------------------------------+ |
| |                                                                            | |
| +----------------------------------------------------------------------------+ |
| [ ] Requires new OMR       [Save draft] [Complete review and next]             |
+--------------------------------------------------------------------------------+
```

### Защита от потери данных

- автосохранение черновика после паузы ввода;
- явный индикатор `saving`, `saved`, `save failed`;
- предупреждение при закрытии страницы с несохранёнными изменениями;
- optimistic locking по номеру версии;
- сообщение о конфликте, если страницу одновременно изменил другой эксперт;
- сохранение каждой завершённой версии без перезаписи предыдущей.

## 4. Данные в базе

### Основные сущности

| Сущность | Ключевые поля |
|---|---|
| `documents` | `id`, `doc_id`, title, authors, year, language, source paths, rights status |
| `pages` | `id`, `document_id`, `page_index`, image paths, width, height, DPI, checksum |
| `detector_runs` | `id`, model/rule version, parameters, started/finished timestamps |
| `page_predictions` | `page_id`, `detector_run_id`, prediction, score, feature snapshot |
| `page_labels` | `id`, `page_id`, page type, has music, comment, source, status, version |
| `page_quality_tags` | `page_id`, tag, value, author, timestamp |
| `artifacts` | owner page/job, kind, path/URI, checksum, size, MIME type, version |
| `processing_jobs` | type, status, priority, attempts, payload, error, timestamps |
| `omr_runs` | `page_id`, engine/version, DPI, parameters, status, log artifact |
| `midi_runs` | source MXL, mode, status, output artifact, error |
| `expert_reviews` | reviewer, status, usability, counters, comments, protocol version |
| `failure_reviews` | failure reason, log excerpt, image issue, decision, reviewer |
| `users` | identity, display name, active status |
| `roles` | operator, expert, developer, administrator |
| `audit_events` | actor, entity, action, before/after snapshot, timestamp |
| `exports` | export type, filters, schema version, artifact, status, timestamp |

### Требования к моделированию

- `doc_id + page_index` должен быть уникальным бизнес-ключом страницы;
- prediction хранится отдельно от ручной метки;
- новая ручная правка создаёт версию, а не уничтожает историю;
- артефакты хранят checksum и версию pipeline;
- файловые данные не помещаются в реляционную БД: в БД хранится URI и метаинформация;
- временные пути не должны быть публичными URL;
- даты сохраняются в UTC;
- свободные комментарии хранятся в UTF-8;
- удаление экспертной оценки выполняется как отмена версии с записью в audit log.

### Минимальная схема `expert_reviews`

```text
id
page_id
omr_run_id
reviewer_id
status                 draft | completed | superseded
protocol_version
checked_measures
correct_measures
reference_notes
matched_notes
pitch_errors
duration_errors
missing_notes
extra_notes
voice_errors
measure_errors
page_usable            yes | partial | no
dominant_error
expert_comment
requires_new_omr
version
created_at
updated_at
completed_at
```

## 5. REST API

API предлагается версионировать префиксом `/api/v1`. FastAPI генерирует OpenAPI-схему, которую следует использовать как контракт для frontend и интеграционных тестов.

### Документы и страницы

| Метод и endpoint | Назначение |
|---|---|
| `GET /documents` | Список документов с фильтрами и прогрессом |
| `GET /documents/{doc_id}` | Метаданные и статистика документа |
| `GET /documents/{doc_id}/pages` | Страницы документа |
| `GET /pages/{page_id}` | Карточка страницы, prediction, label и артефакты |
| `GET /pages/{page_id}/image` | Авторизованная выдача изображения |
| `GET /pages/{page_id}/neighbors` | Предыдущая и следующая страницы |

### Проверка detector

| Метод и endpoint | Назначение |
|---|---|
| `GET /review/detector/queue` | Очередь с фильтрами и пагинацией |
| `POST /pages/{page_id}/labels` | Создать новую версию ручной метки |
| `GET /pages/{page_id}/labels/history` | История исправлений |
| `POST /pages/{page_id}/quality-tags` | Добавить или обновить теги |
| `POST /pages/{page_id}/review/skip` | Вернуть страницу в очередь без решения |

Пример сохранения:

```json
{
  "page_type": "mixed",
  "has_music": true,
  "quality_comment": "photo scan; rotated",
  "quality_tags": ["photo_scan"],
  "needs_review": false,
  "expected_version": 3
}
```

### OMR

| Метод и endpoint | Назначение |
|---|---|
| `GET /omr/jobs` | Список задач OMR |
| `POST /pages/{page_id}/omr-jobs` | Поставить страницу в очередь |
| `GET /omr/jobs/{job_id}` | Статус, параметры и ошибки |
| `POST /omr/jobs/{job_id}/retry` | Создать повторную попытку |
| `POST /omr/jobs/{job_id}/cancel` | Отменить ожидающую задачу |
| `POST /omr/jobs/{job_id}/failure-review` | Сохранить разбор failure |
| `GET /pages/{page_id}/omr-runs` | История OMR-версий |

### Экспертная оценка

| Метод и endpoint | Назначение |
|---|---|
| `GET /review/omr/queue` | Очередь страниц для эксперта |
| `GET /pages/{page_id}/expert-review-context` | Скан, MXL, MIDI и текущий review |
| `POST /pages/{page_id}/expert-reviews` | Создать черновик |
| `PATCH /expert-reviews/{review_id}` | Автосохранить изменения |
| `POST /expert-reviews/{review_id}/complete` | Завершить оценку |
| `GET /pages/{page_id}/expert-reviews` | История оценок |

### Артефакты и экспорт

| Метод и endpoint | Назначение |
|---|---|
| `GET /artifacts/{artifact_id}/download` | Авторизованная загрузка |
| `POST /exports` | Создать CSV/JSON-экспорт |
| `GET /exports/{export_id}` | Статус экспорта |
| `GET /exports/{export_id}/download` | Скачать готовый файл |

### Общие правила API

- пагинация через `limit` и cursor, а не загрузка всей очереди;
- фильтры передаются query-параметрами;
- mutation endpoints требуют аутентификации и роли;
- `409 Conflict` возвращается при несовпадении `expected_version`;
- идемпотентный ключ используется при создании задач;
- ошибки имеют единый JSON-формат с `code`, `message` и `details`;
- тяжёлые операции возвращают `202 Accepted` и идентификатор задачи;
- API не раскрывает абсолютные пути файловой системы.

## 6. Формат задач очереди

Задача должна быть самодостаточной, версионированной и идемпотентной.

### Общий envelope

```json
{
  "job_id": "uuid",
  "job_type": "run_audiveris",
  "schema_version": 1,
  "entity": {
    "doc_id": "rsl01012190186",
    "page_index": 37,
    "page_id": 12345
  },
  "input_artifacts": [
    {
      "artifact_id": "uuid",
      "kind": "omr_page_300dpi",
      "checksum": "sha256:..."
    }
  ],
  "parameters": {
    "dpi": 300,
    "engine": "audiveris",
    "engine_version": "recorded-at-runtime"
  },
  "priority": 50,
  "attempt": 1,
  "max_attempts": 3,
  "idempotency_key": "run_audiveris:page-12345:input-sha:config-sha",
  "requested_by": "user-or-system-id",
  "created_at": "2026-06-08T12:00:00Z",
  "trace_id": "uuid"
}
```

### Типы задач

- `extract_pages`;
- `run_detector`;
- `extract_omr_page`;
- `run_audiveris`;
- `convert_mxl_to_midi`;
- `render_musicxml_preview`;
- `build_research_export`;
- `recompute_metrics`.

### Правила обработки

- worker сначала проверяет idempotency key и существующий валидный результат;
- heartbeat обновляет состояние длинной задачи;
- timeout и максимальное число попыток задаются по типу job;
- Audiveris обрабатывается ограниченным CPU pool;
- результат записывается до подтверждения сообщения очереди;
- после исчерпания retries задача получает статус `failed` и требует разбора;
- повторный запуск создаёт новый attempt, сохраняя предыдущие логи;
- downstream-задача создаётся только после атомарной фиксации результата.

Для пилота допустима очередь на основе таблицы PostgreSQL с `SELECT ... FOR UPDATE SKIP LOCKED`. При росте нагрузки можно выделить специализированный брокер, не меняя формат payload.

## 7. Сохранение исправлений эксперта

### Принцип

Исправления хранятся как неизменяемая история версий. Актуальная метка определяется последней подтверждённой версией, но исходный prediction и прошлые ручные решения остаются доступными.

### Detector review

При сохранении:

1. frontend отправляет новое значение и `expected_version`;
2. backend проверяет права и текущую версию;
3. в одной транзакции создаётся новая запись `page_labels`;
4. сохраняются изменения тегов;
5. в `audit_events` записываются before/after;
6. пересчитывается `needs_review`;
7. при необходимости создаётся OMR-задача;
8. frontend получает новую версию.

### OMR expert review

- черновик можно обновлять;
- завершённая оценка становится неизменяемой;
- исправление завершённой оценки создаёт новую версию;
- повторная экспертиза другим пользователем хранится отдельно;
- агрегированные метрики строятся только по выбранной политике: последняя оценка, согласованная оценка или обе оценки отдельно;
- версия MXL обязательна, поскольку оценка относится к конкретному OMR-результату.

### Одновременное редактирование

Используется optimistic locking:

- клиент передаёт `expected_version`;
- при конфликте сервер возвращает текущую версию;
- пользователь выбирает повторное применение или отказ;
- автоматическое бесшумное перезаписывание запрещено.

## 8. Автоматический экспорт CSV для ВКР

### Назначение

Экспорт создаёт воспроизводимый снимок данных, а не заменяет рабочую БД. Каждый файл сопровождается:

- временем формирования;
- фильтрами;
- версией схемы;
- Git revision кода экспортера, если доступна;
- числом строк;
- checksum;
- описанием источника данных.

### Основные экспорты

| Экспорт | Целевой файл |
|---|---|
| Актуальные page labels | `data/labels/pages_validated_thesis.csv` |
| Экспертная оценка MXL | `data/labels/omr_expert_evaluation_thesis.csv` |
| Разбор OMR failures | `data/labels/omr_failure_expert_review_thesis.csv` |
| Метрики detector | `outputs/reports/music_detector_metrics.csv` |
| OMR pipeline report | `outputs/reports/omr_pipeline_report.csv` |
| Audit snapshot | `outputs/reports/expert_review_audit.csv` |

### Режимы запуска

- вручную из административного интерфейса;
- после завершения заданного набора экспертиз;
- по расписанию;
- перед пересчётом метрик;
- через CLI/API для воспроизводимого эксперимента.

### Последовательность

```text
POST /api/v1/exports
→ задача build_research_export
→ чтение согласованного snapshot БД
→ проверка схемы и ограничений
→ запись временного файла
→ атомарное перемещение в целевой путь
→ checksum и manifest
→ статус ready
```

Если экспортируется файл в `data/labels`, требуется явное подтверждение пользователя. Файлы в `outputs` могут пересоздаваться автоматически, но не должны коммититься. Секреты, абсолютные локальные пути и персональные данные пользователей в исследовательский экспорт не включаются.

## 9. Выбор технологий

### Backend: FastAPI

FastAPI подходит, поскольку:

- проект уже написан на Python;
- можно переиспользовать функции pipeline без отдельного технологического стека;
- типизированные схемы удобно описывать через Pydantic;
- OpenAPI-документация формируется автоматически;
- длительные задания можно отделить от HTTP API;
- удобно писать модульные и интеграционные тесты.

FastAPI отвечает только за API, авторизацию и оркестрацию. Audiveris и тяжёлые batch-задачи выполняются workers.

### База данных: SQLite или PostgreSQL

**SQLite** подходит для:

- локального прототипа;
- одного пользователя;
- демонстрации ВКР;
- минимального развёртывания.

Ограничение SQLite — конкурентная запись и эксплуатация нескольких workers. Файловая БД не должна размещаться на сетевом диске без проверки режима блокировок.

**PostgreSQL** рекомендуется для:

- нескольких операторов и экспертов;
- конкурентных workers;
- транзакций и optimistic locking;
- полноценных индексов и фильтрации очередей;
- эксплуатационного журнала;
- очереди на базе таблицы на первом продуктовом этапе.

Модели и миграции следует проектировать так, чтобы локальный SQLite-пилот переносился в PostgreSQL без изменения бизнес-логики.

### Frontend: React или HTMX

**HTMX** предпочтителен для первого пилота:

- формы detector review;
- фильтры и пагинация;
- серверный HTML;
- небольшое количество клиентского состояния;
- быстрый переход от статической галереи.

**React** оправдан для насыщенного экрана scan + MXL + MIDI:

- независимые панели и масштабирование;
- клиентский MusicXML renderer;
- playback state;
- маркеры тактов;
- автосохранение и сложная форма;
- синхронная навигация.

Практичный путь:

1. FastAPI + server templates + HTMX для dashboard и detector review;
2. отдельный React-компонент или небольшой React frontend для экспертного экрана;
3. переход к полноценному SPA только при подтверждённой необходимости.

Не следует одновременно реализовывать два полных frontend-приложения. Граница должна проходить по сложности интерфейса, а визуальные компоненты и API-контракты должны быть едиными.

### Отрисовка MusicXML: OpenSheetMusicDisplay

OpenSheetMusicDisplay подходит для браузерной отрисовки MusicXML и вывода через SVG/Canvas. Для продукта требуется отдельная проверка:

- корректного открытия MXL и распакованного MusicXML;
- производительности на больших партитурах;
- отображения голосов, текста и нестандартных обозначений;
- соответствия результата тому, что эксперт видит в MuseScore;
- лицензии и способа поставки выбранной версии.

Оригинальный MXL остаётся эталонным артефактом pipeline; browser rendering является представлением для проверки и не должен изменять файл.

### MIDI playback

Рекомендуемый базовый вариант:

- `.mid` хранится как артефакт;
- frontend разбирает MIDI;
- Web Audio воспроизводит его через piano/soundfont;
- состояние playback не влияет на экспертную оценку при сохранении;
- при несовместимости браузера доступно скачивание MIDI.

Дополнительный надёжный fallback — серверное формирование WAV/OGG-превью из MIDI с зафиксированным soundfont. Web MIDI API можно добавить для внешних устройств, но не использовать как обязательную основу playback.

### Рекомендуемый стек пилота

| Слой | Выбор для пилота | Путь масштабирования |
|---|---|---|
| API | FastAPI | FastAPI за reverse proxy |
| DB | SQLite | PostgreSQL |
| Миграции | Alembic | Alembic |
| Основной UI | Jinja templates + HTMX | Сохранить либо постепенно заменить |
| Экспертный UI | React-компонент при необходимости | Отдельный React frontend |
| MusicXML | OpenSheetMusicDisplay | Проверенная и закреплённая версия |
| MIDI | Web Audio + soundfont | Аудиопревью и/или внешние MIDI-устройства |
| Queue | DB-backed jobs | Специализированный брокер при необходимости |
| Workers | Python processes, ограниченный Audiveris pool | Несколько worker-hosts |
| Storage | Локальная файловая система | Объектное или сетевое хранилище |

## 10. Нефункциональные требования

### Надёжность

- ни одна ошибка страницы не останавливает очередь;
- сохранение формы транзакционно;
- задачи идемпотентны;
- артефакты проверяются checksum;
- поддерживаются retries и resume.

### Производительность

- первая страница очереди открывается без загрузки всего корпуса;
- thumbnails используются вместо полноразмерных PNG в списках;
- полноразмерный скан загружается по запросу;
- MusicXML renderer и MIDI загружаются только на экспертном экране;
- Audiveris concurrency задаётся конфигурацией.

### Безопасность

- роли ограничивают изменение меток, запуск OMR и администрирование;
- исходные PDF/MRC не выдаются без авторизации;
- пути файловой системы не раскрываются в API;
- все ручные изменения входят в audit log;
- экспорт учитывает правовой статус документа.

### Воспроизводимость

- фиксируются версии detector, Audiveris, music21 и протокола экспертизы;
- каждая оценка привязана к конкретному MXL;
- CSV формируется из согласованного snapshot;
- схема экспорта версионируется;
- технический success и музыкальная оценка не объединяются в одну метрику.

## 11. Минимальный объём пилота

Для демонстрации архитектуры в рамках ВКР достаточно:

1. FastAPI-приложения с SQLite;
2. авторизации с ролями `operator` и `expert`;
3. очереди detector review;
4. сохранения версионированных page labels;
5. экрана scan + MXL + MIDI для 30 экспертных страниц;
6. формы полей из протокола экспертной проверки;
7. просмотра девяти OMR failures;
8. DB-backed очереди без распределённого брокера;
9. автоматического экспорта двух экспертных CSV;
10. тестов API, валидации и конфликтов версий.

Распределённые workers, PostgreSQL, полнофункциональный React SPA и интеграция с библиотечным каталогом относятся к следующему продуктовому этапу. Их архитектура должна быть предусмотрена, но их реализация не обязательна для доказательства исследовательского результата ВКР.

## 12. Критерии приёмки интерфейса

- оператор может найти спорную страницу, исправить метку и увидеть её историю;
- система не перезаписывает исходный prediction;
- эксперт видит скан и отрисованный MusicXML в одном экране;
- MIDI воспроизводится либо доступен fallback;
- форма не допускает логически противоречивые счётчики;
- черновик восстанавливается после обновления страницы;
- завершённая оценка привязана к версии MXL;
- конфликт одновременного редактирования обнаруживается;
- failure можно классифицировать и направить на повторный запуск;
- CSV для ВКР формируется без ручного копирования значений;
- техническая успешность и экспертная музыкальная пригодность экспортируются раздельно.

## Источники по выбранным web-компонентам

- FastAPI: <https://fastapi.tiangolo.com/>
- HTMX: <https://htmx.org/docs/>
- React: <https://react.dev/>
- OpenSheetMusicDisplay: <https://opensheetmusicdisplay.org/>
- Web MIDI API: <https://developer.mozilla.org/en-US/docs/Web/API/Web_MIDI_API>
- Web Audio API: <https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API>
