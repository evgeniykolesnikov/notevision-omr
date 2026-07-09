# neural_omr_experiment_notes

DOCX VKR, defense PPTX/PDF, the main pipeline and final VKR metrics were not changed. Git was not touched.

## Status

- This is an experimental proof-of-concept.
- It is not a replacement for Audiveris.
- It is not a final VKR metric.
- Training uses pseudo-labels from existing MXL/MusicXML.
- Existing MXL/MusicXML are not expert ground truth.
- The model does not guarantee musical correctness.
- CUDA is used only if available.
- Full neural OMR would require expert-verified image-to-MusicXML pairs.
- The main VKR pipeline remains Audiveris baseline.

## Results

- pairs_found: 368
- dataset_rows_used: 100
- device: cuda
- val_pages: 20
- mean_token_accuracy: 0.1313
- sequence_exact_match: 0.0000
- mean_inference_time_ms: 8.925

## Defense wording

As a future direction, CPU-based Audiveris could be complemented by neural OMR that can use GPU inference. In this project it is only an experimental proof-of-concept, because there is no expert-verified MusicXML ground truth. The prototype is trained on pseudo-labels from already obtained MXL/MusicXML and is not used in final VKR metrics.

## Runtime comparison with Audiveris

See `docs\thesis\local_vkr\neural_vs_audiveris_timing_notes.md`. This comparison is runtime-only and does not compare OMR quality.
