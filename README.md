# NoteVision OMR - pipeline for scanned sheet music documents

NoteVision OMR is an engineering MVP for processing scanned sheet music documents from local PDF/MRC collections. The main pipeline is:

```text
PDF/MRC -> pages -> routing/page classification -> pre-OMR filter
-> Audiveris baseline OMR -> MXL/MusicXML -> MIDI
-> music features -> reports -> review_app -> failure/expert review
```

The project focuses on reproducible local processing, artifact tracking and human-in-the-loop review. It does not claim note-level musical correctness without expert validation.

## Main Features

- PDF page extraction and local document inventory.
- MARC/MRC metadata parsing.
- Page validation and `page_type` routing.
- Pre-OMR filtering to avoid sending obvious non-music pages to OMR.
- Audiveris integration as the baseline OMR engine.
- MXL/MusicXML and MIDI artifact handling.
- Music feature extraction from existing MXL/MusicXML.
- CSV/Markdown reports for corpus, classifier, OMR and failure analysis.
- `review_app` for manual review, failure review and expert review workflows.

## Important Metrics

These are the final VKR metrics and must be treated as technical artifact availability, not musical correctness:

- Corpus: 52 documents.
- Validated pages: 2513.
- Page types: music 2214, mixed 24, title 78, text 69, blank 102, unknown 26.
- OMR-300 diagnostic subset: 300 pages from 39 documents.
- Primary MXL: 240/300 = 80.00%.
- Primary MIDI: 239/300 = 79.67%.
- Final MXL technical success: 257/300 = 85.67%.
- Final MIDI technical success: 256/300 = 85.33%.
- Final failures: 43 pages.
- Failure review: 23 routing/false-positive music cases and 20 real music/mixed OMR cases.
- Pre-OMR filter: 300 candidates, 295 sent to OMR, 5 filtered out, 0 wrongly filtered music/mixed.

`technical success != musical correctness`: MXL/MIDI presence means that a structured/playback artifact was created. It does not prove that notes, rhythm, voices, measures or playback are musically correct.

## Main Pipeline vs Experimental Work

Main pipeline:

- Audiveris baseline OMR.
- MXL/MusicXML and MIDI artifact creation.
- Music feature extraction from MXL/MusicXML.
- Reports and review application.
- Failure review and expert review preparation.

Experimental / backup analyses:

- Pipeline timing benchmarks.
- Audiveris timing sample.
- Safe parallel OMR batch runner.
- Music features coverage analysis.
- Toy neural OMR prototype.
- Neural vs Audiveris runtime comparison.

The experimental neural OMR prototype predicts simplified token sequences and does not replace Audiveris.

## Repository Structure

```text
scripts/                         command-line pipeline and analysis scripts
src/notevision/                  main Python package
src/notevision/omr/              Audiveris, OMR and related helpers
src/notevision/experimental/     experimental research prototypes
review_app/                      local web interface for review
tests/                           unit tests
docs/thesis/local_vkr/           VKR notes, defense materials and local reports
outputs/                         generated artifacts and reports, not for Git
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Some optional scripts require external tools such as Audiveris, MuseScore/music21 or local CUDA-enabled PyTorch. Audiveris can be passed explicitly:

```powershell
python scripts/run_audiveris_omr.py --help
python scripts/run_audiveris_omr.py --audiveris-bin "C:\Program Files\Audiveris\Audiveris.exe" --help
```

## Typical Commands

Parse MRC metadata:

```powershell
python scripts/parse_mrc.py --document-dir data/raw/<doc_id> --out outputs/reports/<doc_id>_metadata.json
python scripts/parse_mrc_batch.py --raw-dir data/raw --out outputs/reports/all_metadata.csv
```

Extract PDF pages:

```powershell
python scripts/extract_pages.py --document-dir data/raw/<doc_id> --out outputs/pages/<doc_id> --dpi 200
```

Run OMR evaluation pipeline:

```powershell
python scripts/run_omr_eval_pipeline.py --help
```

Convert MXL to MIDI:

```powershell
python scripts/convert_mxl_to_midi.py --input outputs/omr_eval_300/<doc_id>/page_001/page_001.mxl --out outputs/midi_eval_300/<doc_id>/page_001.mid
```

Run the local review app:

```powershell
$env:REVIEW_APP_PASSWORD = "change-me"
uvicorn review_app.main:app --host 127.0.0.1 --port 8000
```

Run tests:

```powershell
python -m unittest discover -s tests
```

Run timing and availability analyses:

```powershell
python scripts/benchmark_pipeline_stages.py --sample-size 50 --only-existing-omr --include-music-features --output outputs/reports/music_features_timing_report.md
python scripts/analyze_all_pages_music_features_availability.py
python scripts/benchmark_omr_timing_sample.py --sample-size 10 --audiveris-bin "C:\Program Files\Audiveris\Audiveris.exe"
```

Run the safe experimental parallel batch runner:

```powershell
python scripts/run_omr_batch_parallel.py --max-pages 20 --workers 2 --only-without-mxl --dry-run
python scripts/run_omr_batch_parallel.py --max-pages 10 --workers 2 --only-without-mxl --run --output-dir outputs/omr_batch_parallel_test --midi-output-dir outputs/midi_batch_parallel_test --audiveris-bin "C:\Program Files\Audiveris\Audiveris.exe"
```

Run the experimental toy neural OMR prototype:

```powershell
python scripts/train_neural_omr_toy.py --epochs 1 --batch-size 4 --image-size 224 --max-samples 100 --output-dir outputs/experiments/neural_omr_toy
python scripts/evaluate_neural_omr_toy.py --output-dir outputs/experiments/neural_omr_toy
python scripts/compare_neural_vs_audiveris_timing.py --model-dir outputs/experiments/neural_omr_toy
```

## Data Policy

- Raw PDFs/MRC files remain local.
- Generated outputs remain local.
- Do not add `outputs/`, `model.pt`, MXL/MusicXML, MIDI, PNG/JPG scans, PDF, DOCX, PPTX or review databases to Git.
- Git should track source code, tests and lightweight documentation/notes only.

## Limitations

- Audiveris is CPU/Java-based and is the main runtime bottleneck.
- GPU does not directly accelerate Audiveris.
- Technical success is not musical correctness.
- Music features are extracted from MXL/MusicXML, not directly from PNG pages.
- Absence of music features does not mean absence of music on a scanned page.
- Full neural OMR requires expert-verified image-to-MusicXML ground truth.
- Search or identification against a music database is future work.

## Defense Note

This repository contains the engineering MVP for the VKR project. Experimental modules are included for research and future-work analysis. They do not change the final VKR metrics and do not replace the Audiveris baseline.
