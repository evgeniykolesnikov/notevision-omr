# omr_timing_sample_notes

DOCX VKR, defense PPTX/PDF and final VKR metrics were not changed. Git was not touched.

## Scope

- Audiveris was invoked only for the selected timing sample.
- Sample pages: 10.
- Outputs were isolated under `outputs/omr_timing_sample/` and `outputs/midi_timing_sample/`.
- Existing OMR-300/fallback outputs were not overwritten.

## Results

- MXL created: 8.
- MIDI created: 8.
- Music features extracted: 8.
- Mean page preprocessing time: 3.055 ms.
- Mean Audiveris time per selected page: 8617.722 ms.
- Mean MIDI conversion time: 181.959 ms.
- Mean music features extraction time: 13.124 ms.
- Mean total time per page: 8777.476 ms.

## Rough extrapolation

- remaining_music_mixed_without_mxl: 1873.
- estimated_total_time_hours: 4.57.
- This is a rough estimate from a small sample and does not change final VKR metrics. The estimate uses mean total time over all 10 selected pages, including 2 pages where Audiveris stopped early without MXL export.

## Defense wording

Music features are extracted from MXL/MusicXML, so pages without MXL require OMR first. A separate benchmark shows that preprocessing and feature extraction take milliseconds, while the main computational cost comes from Audiveris. A full run over all music/mixed pages is a separate batch task and was not mixed with final VKR metrics.

## Outputs

- Sample pages: `outputs\reports\omr_timing_sample_pages.csv`
- Raw timing: `outputs\reports\omr_timing_sample_raw.csv`
- Report: `outputs\reports\omr_timing_sample_report.md`
