# neural_vs_audiveris_timing_notes

DOCX VKR, defense PPTX/PDF, the main pipeline and final VKR metrics were not changed. Git was not touched.

- pages_compared: 10
- neural_device: cuda
- mean_neural_total_ms: 53.085
- mean_audiveris_total_ms: 8777.476
- mean_audiveris_omr_ms: 8617.722
- speedup_by_total_time: 165.35
- mean_neural_cpu_inference_ms: 13.727
- mean_neural_cuda_inference_ms: 16.799
- cuda_speedup: 0.82
- On this tiny model, CUDA inference was not faster on average because GPU launch/data-transfer overhead dominates such a small network. This should not be generalized to a full neural OMR architecture.

## Defense wording

Audiveris and the experimental neural OMR model solve tasks of different completeness. Audiveris builds full MXL/MusicXML, while the toy neural prototype predicts a simplified token sequence. Therefore this is only a runtime comparison and an illustration of possible GPU-oriented development. It does not prove musical correctness and does not replace final VKR metrics.
