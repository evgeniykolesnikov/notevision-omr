# NoteVision OMR Experiments

This document summarizes the current thesis-stage experiments for the
NoteVision OMR pipeline. The numbers describe technical artifact availability
and routing diagnostics; they do not prove musical correctness of MusicXML or
MIDI content.

## Dataset Overview

- Available PDF documents: 51.
- Extracted pages: 2513.
- Diagnostic OMR sample: 300 pages.

The diagnostic sample is used to evaluate the practical pipeline:

```text
page candidates -> Audiveris OMR -> MXL -> MIDI -> fallback analysis
```

## OMR Evaluation

Primary OMR was run on the 300-page diagnostic sample.

| Stage | Result | Rate |
|---|---:|---:|
| Primary MXL | 240 / 300 | 80.00% |
| Primary MIDI | 239 / 300 | 79.67% |
| 400 DPI fallback recovered | +16 | - |
| Preprocessing fallback recovered | +1 | - |
| Final MXL | 257 / 300 | 85.67% |
| Final MIDI | 256 / 300 | 85.33% |

The fallback stages are reported separately because they are recovery
experiments, not replacements for the primary 300 DPI OMR metric.

## Manual Failure Review

After all fallback stages, 43 pages remained as final failures out of the
300-page diagnostic sample.

Manual review showed that final failures contain two different categories:

- routing errors / `false_positive_music`: 23 / 43 = 53.49%;
- real `music` / `mixed` OMR cases: 20 / 43 = 46.51%.

This distinction is important for the thesis. Not every final failure is a
real Audiveris or MusicXML export problem. Some pages should not have been sent
to OMR at all, for example title, cover, text, or blank pages that were routed
as music candidates.

## Experimental Pre-OMR Filter

An experimental conservative pre-OMR filter was evaluated before Audiveris. It
uses lightweight image features and attempts to exclude obvious non-music pages
such as blank, title, text, cover, and decorative pages.

Current diagnostic result:

- filtered out: 5 / 300;
- `false_positive_music` filtered: 5 / 23 = 21.74%;
- wrongly filtered `music` / `mixed`: 0 / 282.

The filter is intentionally conservative. It does not replace the main page
classifier and does not replace the Audiveris pipeline. Its role is to reduce
avoidable OMR launches and to provide additional evidence for future classifier
improvement.

## Interpretation

The OMR experiment shows that the pipeline can produce MXL/MIDI artifacts for a
large share of pages, but the remaining failures must be interpreted carefully.

Routing errors are useful as hard negatives for improving the page classifier.
Real OMR failures require separate work on preprocessing, alternative OMR
settings, or manual expert review.

The pre-OMR filter currently removes only a small number of false positives,
but it does so without excluding music/mixed pages in the diagnostic sample.
This makes it a safe experimental component, not yet a complete solution.
