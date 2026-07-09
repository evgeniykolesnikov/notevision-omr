# omr_batch_parallel_speedup_notes

DOCX VKR, defense PPTX/PDF and final VKR metrics were not changed. Git was not touched.

## What was created

- `scripts/run_omr_batch_parallel.py`
- `tests/test_run_omr_batch_parallel.py`
- `outputs/reports/omr_batch_parallel_dry_run_report.md`
- `outputs/reports/omr_batch_parallel_dry_run_raw.csv`
- `outputs/reports/omr_batch_parallel_test_worker1_report.md`
- `outputs/reports/omr_batch_parallel_test_worker1_raw.csv`
- `outputs/reports/omr_batch_parallel_test_report.md`
- `outputs/reports/omr_batch_parallel_test_raw.csv`

## Safety

- Default mode is dry-run; real OMR requires `--run`.
- `--max-pages` is required to stay small and is capped by the script.
- Existing MXL/MusicXML pages are skipped when `--only-without-mxl` is used.
- Existing target-output MXL files are skipped.
- OMR-300 and fallback output folders are explicitly refused as targets.
- Outputs were isolated under `outputs/omr_batch_parallel_test_w1/`, `outputs/midi_batch_parallel_test_w1/`, `outputs/omr_batch_parallel_test/`, and `outputs/midi_batch_parallel_test/`.

## Dry-run

- Command selected 20 pages.
- Audiveris was not launched.
- Report: `outputs/reports/omr_batch_parallel_dry_run_report.md`.

## Real runs

| mode | processed | MXL | MIDI | features | failures | wall_seconds | mean_audiveris_ms | mean_total_ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| workers=1 | 10 | 10 | 10 | 10 | 0 | 104.195 | 10125.666 | 10419.31 |
| workers=2 | 10 | 10 | 10 | 10 | 0 | 58.245 | 11257.581 | 11584.457 |

Speedup workers=2 vs workers=1 by wall time: 1.79x.

The workers=2 run was stable on the 10-page sample. Per-page Audiveris time increased because two Audiveris processes compete for local resources, but wall-clock time decreased.

## Rough estimate for 1873 pages

| workers | estimated total time | comment |
|---:|---:|---|
| 1 | 5.42 h | based on observed workers=1 wall time |
| 2 | 3.03 h | based on observed workers=2 wall time |
| 4 | 1.36 h | idealized estimate from workers=1, not directly measured |

This is a rough estimate from a small sample. It is not a final runtime guarantee and does not change VKR metrics.

## Can it be scaled safely?

It can be scaled cautiously as a separate batch task: start with resume-enabled chunks, keep `--only-without-mxl`, write to isolated output folders, and monitor Audiveris logs. Workers=2 looked safe on the small sample. Workers=4 was not run and should be tested separately before use.

## Defense wording

Главный вычислительный этап - Audiveris. Ускорение возможно не за счет извлечения music features, а за счет того, что мы не отправляем в OMR лишние страницы, кэшируем уже полученные MXL/MIDI и можем запускать независимые страницы параллельно. Полный корпусный batch не смешивается с финальными метриками ВКР.
