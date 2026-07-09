# all_pages_music_features_availability_notes

DOCX VKR, defense PPTX/PDF and final VKR metrics were not changed. Git was not touched. Audiveris was not invoked.

## Scope

- All validated pages of the corpus were accounted for: 2513.
- Music features are extracted only from already existing MXL/MusicXML.
- Absence of features on a page does not mean absence of music.
- For pages without MXL/MusicXML, an OMR step is needed before music-feature extraction can be evaluated.
- OMR-300 availability in this note reflects existing artifacts found in the workspace and does not replace final OMR-300 technical-success metrics in the VKR.
- This is not musical correctness and not expert validation.

## All pages

- pages_with_png: 2513.
- pages_with_mxl: 370.
- pages_with_midi: 364.
- pages_with_parsed_music_features: 368.
- pages_without_mxl: 2143.

## Music/mixed pages

- total: 2238.
- pages_with_mxl: 365.
- pages_with_midi: 359.
- pages_with_parsed_music_features: 363.
- pages_without_mxl: 1873.

## OMR-300 pages

- total: 300.
- pages_with_mxl: 261.
- pages_with_midi: 259.
- pages_with_parsed_music_features: 259.
- pages_without_mxl: 39.

## Defense wording

We accounted for all validated corpus pages and matched them with existing OMR artifacts. Music features are extracted only where MXL/MusicXML already exists. Therefore feature coverage is calculated separately from OMR technical success.

## Outputs

- Report: `outputs\reports\all_pages_music_features_availability_report.md`
- CSV: `outputs\reports\all_pages_music_features_availability.csv`
