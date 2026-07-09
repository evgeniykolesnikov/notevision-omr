"""Benchmark safe NoteVision OMR pipeline stages on existing artifacts.

The default run does not invoke Audiveris and does not overwrite existing
MIDI files. It measures lightweight page preprocessing/binarization and
MusicXML feature extraction from files that are already present locally.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from notevision.music_features import (  # noqa: E402
    extract_music_features,
    find_musicxml_files,
    identify_musicxml_page,
)

cv2 = None

try:
    import numpy as np
except Exception:  # pragma: no cover - exercised only without NumPy.
    np = None

try:
    from PIL import Image, ImageFilter
except Exception:  # pragma: no cover - exercised only without Pillow.
    Image = None
    ImageFilter = None

DEFAULT_OUTPUT = PROJECT_ROOT / "outputs" / "reports" / "pipeline_stage_timing_report.md"
DEFAULT_RAW = PROJECT_ROOT / "outputs" / "reports" / "pipeline_stage_timing_raw.csv"
DEFAULT_PROBE = PROJECT_ROOT / "outputs" / "reports" / "binarization_routing_feature_probe.csv"
DEFAULT_NOTES = PROJECT_ROOT / "docs" / "thesis" / "local_vkr" / "pipeline_timing_and_binarization_notes.md"
DEFAULT_LABELS = PROJECT_ROOT / "data" / "labels" / "pages_validated_thesis.csv"
DEFAULT_MXL_ROOTS = [
    PROJECT_ROOT / "outputs" / "omr_eval_300",
    PROJECT_ROOT / "outputs" / "omr_eval_300_400dpi_fallback",
    PROJECT_ROOT / "outputs" / "omr_eval_300_preprocessed_fallback",
    PROJECT_ROOT / "outputs" / "omr_eval_300_pipeline_test" / "primary_omr",
    PROJECT_ROOT / "outputs" / "omr",
]

RAW_COLUMNS = [
    "stage",
    "doc_id",
    "page_index",
    "input_path",
    "output_path",
    "success",
    "duration_ms",
    "error",
]

PROBE_COLUMNS = [
    "doc_id",
    "page_index",
    "page_type",
    "has_music",
    "image_path",
    "black_pixel_ratio",
    "horizontal_projection_strength",
    "connected_components_count",
    "contrast",
    "binarization_method",
    "processing_time_ms",
    "error",
]


@dataclass(frozen=True)
class PageSample:
    doc_id: str
    page_index: str
    image_path: Path
    page_type: str = ""
    has_music: str = ""


@dataclass(frozen=True)
class MxlSample:
    doc_id: str
    page_index: str
    source_path: Path


def timed_call(func: Callable[[], object]) -> tuple[object | None, float, str]:
    """Run a callable and return result, duration in milliseconds, and error."""
    start = time.perf_counter()
    try:
        result = func()
        error = ""
    except Exception as exc:  # noqa: BLE001 - report row must capture any failure.
        result = None
        error = str(exc)
    duration_ms = (time.perf_counter() - start) * 1000.0
    return result, duration_ms, error


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def _parse_page_index(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "unknown"
    try:
        return str(int(float(text)))
    except ValueError:
        return text


def collect_page_samples(
    *,
    labels_path: Path = DEFAULT_LABELS,
    sample_size: int,
    doc_id: str | None = None,
) -> list[PageSample]:
    """Collect existing page PNG samples from validated labels."""
    samples: list[PageSample] = []
    for row in _read_csv(labels_path):
        row_doc_id = str(row.get("doc_id", "")).strip()
        if doc_id and row_doc_id != doc_id:
            continue
        image_value = str(row.get("image_path", "")).strip()
        if not image_value:
            continue
        image_path = Path(image_value)
        if not image_path.is_absolute():
            image_path = PROJECT_ROOT / image_path
        if not image_path.is_file():
            continue
        samples.append(
            PageSample(
                doc_id=row_doc_id or "unknown",
                page_index=_parse_page_index(row.get("page_index")),
                image_path=image_path,
                page_type=str(row.get("page_type", "")).strip(),
                has_music=str(row.get("has_music", "")).strip(),
            )
        )
        if len(samples) >= sample_size:
            break
    return samples


def collect_mxl_samples(
    *,
    roots: Iterable[Path] = DEFAULT_MXL_ROOTS,
    sample_size: int,
    doc_id: str | None = None,
) -> list[MxlSample]:
    """Collect existing MXL/MusicXML files without running OMR."""
    samples: list[MxlSample] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in find_musicxml_files(root, recursive=True):
            resolved = path.resolve()
            if resolved in seen:
                continue
            inferred_doc_id, inferred_page_index, _ = identify_musicxml_page(path)
            if doc_id and inferred_doc_id != doc_id:
                continue
            seen.add(resolved)
            samples.append(
                MxlSample(
                    doc_id=inferred_doc_id,
                    page_index=inferred_page_index,
                    source_path=path,
                )
            )
            if len(samples) >= sample_size:
                return samples
    return samples


def load_grayscale_resized(image_path: Path, max_width: int = 1200) -> object:
    """Load image, convert to grayscale, and resize large pages for timing."""
    if cv2 is not None:
        image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError(f"Could not read page image: {image_path}")
        height, width = image.shape[:2]
        if width > max_width:
            scale = max_width / width
            image = cv2.resize(
                image,
                (max_width, max(1, int(height * scale))),
                interpolation=cv2.INTER_AREA,
            )
        return image

    if Image is None or np is None:
        raise RuntimeError("Pillow and NumPy are required without OpenCV.")
    with Image.open(image_path) as source:
        gray = source.convert("L")
        width, height = gray.size
        if width > max_width:
            scale = max_width / width
            gray = gray.resize(
                (max_width, max(1, int(height * scale))),
                Image.Resampling.LANCZOS,
            )
        return np.asarray(gray)


def otsu_binary(gray: object) -> object:
    """Build a foreground binary image with Otsu threshold."""
    if cv2 is not None:
        _, binary = cv2.threshold(
            gray,
            0,
            255,
            cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
        )
        return binary
    if np is None:
        raise RuntimeError("NumPy is required for Otsu binarization.")
    values = np.asarray(gray, dtype=np.uint8)
    hist = np.bincount(values.ravel(), minlength=256).astype(float)
    total = values.size
    sum_total = float(np.dot(np.arange(256), hist))
    sum_background = 0.0
    weight_background = 0.0
    max_variance = -1.0
    threshold = 0
    for level in range(256):
        weight_background += hist[level]
        if weight_background == 0:
            continue
        weight_foreground = total - weight_background
        if weight_foreground == 0:
            break
        sum_background += level * hist[level]
        mean_background = sum_background / weight_background
        mean_foreground = (sum_total - sum_background) / weight_foreground
        variance = weight_background * weight_foreground * (
            mean_background - mean_foreground
        ) ** 2
        if variance > max_variance:
            max_variance = variance
            threshold = level
    return np.where(values < threshold, 255, 0).astype(np.uint8)


def adaptive_binary(gray: object) -> object:
    """Build a foreground binary image with adaptive threshold."""
    if cv2 is not None:
        return cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            35,
            11,
        )
    if Image is None or ImageFilter is None or np is None:
        raise RuntimeError("Pillow and NumPy are required without OpenCV.")
    values = np.asarray(gray, dtype=np.uint8)
    image = Image.fromarray(values)
    local_mean = np.asarray(image.filter(ImageFilter.BoxBlur(17)), dtype=np.int16)
    return np.where(values.astype(np.int16) < local_mean - 11, 255, 0).astype(
        np.uint8
    )


def calculate_binary_probe_features(binary: object, gray: object) -> dict[str, object]:
    """Calculate simple routing-oriented features from a binary page."""
    if np is None:
        raise RuntimeError("NumPy is required for feature probe.")
    height, width = binary.shape[:2]
    pixel_count = max(width * height, 1)
    black_pixel_ratio = float(np.count_nonzero(binary) / pixel_count)
    row_foreground = np.count_nonzero(binary, axis=1) / max(width, 1)
    horizontal_projection_strength = float(np.percentile(row_foreground, 95))
    if cv2 is not None:
        connected_components_count = int(cv2.connectedComponents(binary)[0] - 1)
    else:
        connected_components_count = connected_component_count(binary)
    contrast = float(np.std(gray) / 255.0)
    return {
        "black_pixel_ratio": black_pixel_ratio,
        "horizontal_projection_strength": horizontal_projection_strength,
        "connected_components_count": connected_components_count,
        "contrast": contrast,
    }


def connected_component_count(binary: object) -> int:
    """Count foreground components with a small dependency-light fallback."""
    if np is None:
        raise RuntimeError("NumPy is required for connected components.")
    foreground = np.asarray(binary) > 0
    height, width = foreground.shape[:2]
    scale = max(width / 320, height / 450, 1.0)
    if scale > 1.0:
        ys = (np.arange(max(1, int(height / scale))) * scale).astype(int)
        xs = (np.arange(max(1, int(width / scale))) * scale).astype(int)
        foreground = foreground[np.ix_(ys.clip(max=height - 1), xs.clip(max=width - 1))]
        height, width = foreground.shape[:2]
    visited = np.zeros((height, width), dtype=bool)
    count = 0
    for y in range(height):
        for x in range(width):
            if not foreground[y, x] or visited[y, x]:
                continue
            count += 1
            stack = [(y, x)]
            visited[y, x] = True
            while stack:
                cy, cx = stack.pop()
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if (
                        0 <= ny < height
                        and 0 <= nx < width
                        and foreground[ny, nx]
                        and not visited[ny, nx]
                    ):
                        visited[ny, nx] = True
                        stack.append((ny, nx))
    return count


def run_page_timing(samples: list[PageSample]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Measure page preprocessing, binarization, and binary feature probe."""
    raw_rows: list[dict[str, object]] = []
    probe_rows: list[dict[str, object]] = []

    for sample in samples:
        gray, duration_ms, error = timed_call(
            lambda path=sample.image_path: load_grayscale_resized(path)
        )
        raw_rows.append(
            raw_row(
                "page_preprocessing_grayscale_resize",
                sample.doc_id,
                sample.page_index,
                sample.image_path,
                "",
                not error,
                duration_ms,
                error,
            )
        )
        if error:
            probe_rows.append(probe_error_row(sample, "otsu", duration_ms, error))
            continue

        for method, func in (("otsu", otsu_binary), ("adaptive", adaptive_binary)):
            binary, bin_ms, bin_error = timed_call(lambda f=func, g=gray: f(g))
            raw_rows.append(
                raw_row(
                    f"binarization_{method}",
                    sample.doc_id,
                    sample.page_index,
                    sample.image_path,
                    "",
                    not bin_error,
                    bin_ms,
                    bin_error,
                )
            )
            if bin_error:
                if method == "otsu":
                    probe_rows.append(probe_error_row(sample, method, bin_ms, bin_error))
                continue
            if method != "otsu":
                continue
            features, feat_ms, feat_error = timed_call(
                lambda b=binary, g=gray: calculate_binary_probe_features(b, g)
            )
            raw_rows.append(
                raw_row(
                    "routing_binary_feature_probe",
                    sample.doc_id,
                    sample.page_index,
                    sample.image_path,
                    "",
                    not feat_error,
                    feat_ms,
                    feat_error,
                )
            )
            probe_rows.append(
                probe_feature_row(sample, features, method, feat_ms, feat_error)
            )
    return raw_rows, probe_rows


def run_music_feature_timing(samples: list[MxlSample]) -> list[dict[str, object]]:
    """Measure music feature extraction from existing MXL/MusicXML files."""
    rows: list[dict[str, object]] = []
    for sample in samples:
        result, duration_ms, error = timed_call(
            lambda path=sample.source_path: extract_music_features(path)
        )
        status_error = ""
        success = not error
        if isinstance(result, dict):
            status = str(result.get("extraction_status", ""))
            success = success and status not in {"missing_file", "parse_error"}
            status_error = str(result.get("error", ""))
        rows.append(
            raw_row(
                "music_features_extraction",
                sample.doc_id,
                sample.page_index,
                sample.source_path,
                "",
                success,
                duration_ms,
                error or status_error,
            )
        )
    return rows


def run_midi_conversion_timing(samples: list[MxlSample], output_root: Path) -> list[dict[str, object]]:
    """Measure MXL to MIDI conversion into a temporary benchmark folder."""
    try:
        from scripts.convert_mxl_to_midi import convert_mxl_to_midi
    except Exception as import_error:  # pragma: no cover - optional stage dependency.
        return [
            raw_row(
                "midi_conversion",
                sample.doc_id,
                sample.page_index,
                sample.source_path,
                "",
                False,
                0.0,
                f"convert_mxl_to_midi could not be imported: {import_error}",
            )
            for sample in samples
        ]
    rows: list[dict[str, object]] = []
    for sample in samples:
        midi_path = output_root / sample.doc_id / f"page_{int(float(sample.page_index)):03d}.mid"
        result, duration_ms, error = timed_call(
            lambda source=sample.source_path, out=midi_path: convert_mxl_to_midi(source, out)
        )
        success = not error and isinstance(result, dict) and result.get("status") == "success"
        rows.append(
            raw_row(
                "midi_conversion",
                sample.doc_id,
                sample.page_index,
                sample.source_path,
                midi_path,
                success,
                duration_ms,
                error or (str(result.get("message", "")) if isinstance(result, dict) else ""),
            )
        )
    return rows


def run_optional_audiveris_timing(
    samples: list[PageSample],
    output_root: Path,
    audiveris_bin: str,
) -> list[dict[str, object]]:
    """Run Audiveris only for a tiny explicit sample."""
    try:
        from notevision.omr.audiveris import run_audiveris
    except Exception as import_error:  # pragma: no cover - optional stage dependency.
        return [
            raw_row(
                "audiveris_omr_tiny_explicit_sample",
                sample.doc_id,
                sample.page_index,
                sample.image_path,
                "",
                False,
                0.0,
                f"run_audiveris could not be imported: {import_error}",
            )
            for sample in samples[:5]
        ]
    rows: list[dict[str, object]] = []
    for sample in samples[:5]:
        output_dir = output_root / sample.doc_id / f"page_{int(float(sample.page_index)):03d}"
        result, duration_ms, error = timed_call(
            lambda inp=sample.image_path, out=output_dir: run_audiveris(
                inp,
                out,
                audiveris_bin=audiveris_bin,
            )
        )
        success = not error and isinstance(result, dict) and result.get("status") == "success"
        rows.append(
            raw_row(
                "audiveris_omr_tiny_explicit_sample",
                sample.doc_id,
                sample.page_index,
                sample.image_path,
                output_dir,
                success,
                duration_ms,
                error or (str(result.get("message", "")) if isinstance(result, dict) else ""),
            )
        )
    return rows


def raw_row(
    stage: str,
    doc_id: str,
    page_index: str,
    input_path: Path,
    output_path: Path | str,
    success: bool,
    duration_ms: float,
    error: str,
) -> dict[str, object]:
    return {
        "stage": stage,
        "doc_id": doc_id,
        "page_index": page_index,
        "input_path": _relative(Path(input_path)),
        "output_path": _relative(Path(output_path)) if output_path else "",
        "success": int(success),
        "duration_ms": round(duration_ms, 3),
        "error": error,
    }


def probe_feature_row(
    sample: PageSample,
    features: object | None,
    method: str,
    duration_ms: float,
    error: str,
) -> dict[str, object]:
    data = features if isinstance(features, dict) else {}
    return {
        "doc_id": sample.doc_id,
        "page_index": sample.page_index,
        "page_type": sample.page_type,
        "has_music": sample.has_music,
        "image_path": _relative(sample.image_path),
        "black_pixel_ratio": data.get("black_pixel_ratio", ""),
        "horizontal_projection_strength": data.get("horizontal_projection_strength", ""),
        "connected_components_count": data.get("connected_components_count", ""),
        "contrast": data.get("contrast", ""),
        "binarization_method": method,
        "processing_time_ms": round(duration_ms, 3),
        "error": error,
    }


def probe_error_row(sample: PageSample, method: str, duration_ms: float, error: str) -> dict[str, object]:
    return probe_feature_row(sample, {}, method, duration_ms, error)


def summarize_stage(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Build per-stage timing summary."""
    summaries: list[dict[str, object]] = []
    for stage in sorted({str(row["stage"]) for row in rows}):
        stage_rows = [row for row in rows if row["stage"] == stage]
        durations = [float(row["duration_ms"]) for row in stage_rows]
        successes = [row for row in stage_rows if str(row["success"]) in {"1", "True", "true"}]
        failed = len(stage_rows) - len(successes)
        summaries.append(
            {
                "stage": stage,
                "count": len(stage_rows),
                "success": len(successes),
                "failed": failed,
                "mean_ms": round(statistics.fmean(durations), 3) if durations else "",
                "median_ms": round(statistics.median(durations), 3) if durations else "",
                "min_ms": round(min(durations), 3) if durations else "",
                "max_ms": round(max(durations), 3) if durations else "",
                "total_seconds": round(sum(durations) / 1000.0, 3),
            }
        )
    return summaries


def write_csv(path: Path, rows: list[dict[str, object]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown_report(
    path: Path,
    *,
    args: argparse.Namespace,
    summary_rows: list[dict[str, object]],
    raw_path: Path,
    probe_path: Path | None,
    page_count: int,
    mxl_count: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Pipeline stage timing report",
        "",
        f"- Run timestamp: {datetime.now().isoformat(timespec='seconds')}",
        f"- Sample size requested: {args.sample_size}",
        f"- Document filter: {args.doc_id or 'none'}",
        f"- Pages measured: {page_count}",
        f"- MXL/MusicXML files measured: {mxl_count}",
        f"- Audiveris invoked: {'yes, tiny explicit sample' if args.include_omr_existing_sample else 'no'}",
        f"- Raw CSV: `{_relative(raw_path)}`",
    ]
    if probe_path is not None:
        lines.append(f"- Binarization feature probe CSV: `{_relative(probe_path)}`")
    lines.extend(
        [
            "",
            "## Timing summary",
            "",
            "| stage | count | success | failed | mean_ms | median_ms | min_ms | max_ms | total_seconds |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in summary_rows:
        lines.append(
            "| {stage} | {count} | {success} | {failed} | {mean_ms} | {median_ms} | {min_ms} | {max_ms} | {total_seconds} |".format(
                **row
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation limits",
            "",
            "- This report measures selected existing local files only.",
            "- Default mode does not rerun Audiveris and does not change final VKR metrics.",
        ]
    )
    if any(str(row["stage"]).startswith("binarization_") for row in summary_rows):
        lines.append(
            "- Binarization is measured as a feature probe/preprocessing candidate, not as proof of classifier quality improvement."
        )
    lines.extend(
        [
            "- Technical timing results do not imply musical correctness of MXL/MIDI.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_notes(
    path: Path,
    *,
    args: argparse.Namespace,
    summary_rows: list[dict[str, object]],
    command: str,
    audiveris_invoked: bool,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    by_stage = {str(row["stage"]): row for row in summary_rows}
    music = by_stage.get("music_features_extraction")
    otsu = by_stage.get("binarization_otsu")
    adaptive = by_stage.get("binarization_adaptive")
    measured_stages = set(by_stage)
    heaviest = max(
        summary_rows,
        key=lambda row: float(row["mean_ms"] or 0.0),
        default=None,
    )
    lines = [
        f"# {path.stem}",
        "",
        "DOCX VKR and defense PPTX/PDF were not changed. Git was not touched.",
        "",
        "## What was measured",
        "",
    ]
    if "page_preprocessing_grayscale_resize" in measured_stages:
        lines.append("- Page preprocessing / grayscale / resize on existing PNG pages.")
    if {"binarization_otsu", "binarization_adaptive"}.intersection(measured_stages):
        lines.append("- Otsu and adaptive binarization on existing PNG pages.")
    if "routing_binary_feature_probe" in measured_stages:
        lines.append("- Binarization-based routing feature probe on existing PNG pages.")
    if "music_features_extraction" in measured_stages:
        lines.append("- Music features extraction from existing MXL/MusicXML files.")
    if args.include_midi_conversion:
        lines.append("- MXL -> MIDI conversion into `outputs/tmp_benchmark_midi/`.")
    if audiveris_invoked:
        lines.append("- Audiveris on a tiny explicit sample only.")
    else:
        lines.append("- Audiveris was not invoked.")
    lines.extend(["", "## Timing observations", ""])
    if heaviest:
        lines.append(
            f"- Heaviest measured stage in this run: `{heaviest['stage']}` with mean {heaviest['mean_ms']} ms."
        )
    if music:
        lines.append(
            f"- MXL/MusicXML files selected for this benchmark: {music['count']}."
        )
        lines.append(f"- Successfully processed: {music['success']}.")
        lines.append(f"- Failed: {music['failed']}.")
        if int(music["success"]) > 0:
            lines.append(
                f"- Music features extraction: mean {music['mean_ms']} ms, median {music['median_ms']} ms per successful/attempted file on this sample."
            )
            lines.append(
                f"- Min/max for music features extraction: {music['min_ms']} ms / {music['max_ms']} ms per file."
            )
        else:
            lines.append(
                "- Music features extraction was attempted, but no files were parsed successfully in this environment; do not use its timing as a real extraction measurement."
            )
    if otsu:
        lines.append(
            f"- Otsu binarization: mean {otsu['mean_ms']} ms, median {otsu['median_ms']} ms per page on this sample."
        )
    if adaptive:
        lines.append(
            f"- Adaptive binarization: mean {adaptive['mean_ms']} ms, median {adaptive['median_ms']} ms per page on this sample."
        )
    lines.extend(
        [
            "",
            "## Can this be used in the defense?",
            "",
            "Yes, carefully. It is safe to say that pipeline stages were measured separately on a selected local sample. Use only stages with successful measurements as timing evidence. Do not claim that OMR itself was accelerated unless Audiveris is measured separately.",
            "",
            "## What cannot be claimed",
            "",
            "- Do not claim that OMR became faster if Audiveris was not benchmarked.",
            "- Do not claim that MXL/MIDI musical correctness was evaluated by this timing run.",
        ]
    )
    if "routing_binary_feature_probe" in measured_stages:
        lines.append(
            "- Do not claim that binarization improved routing accuracy without separate classifier evaluation."
        )
    lines.extend(["", "## Defense wording", ""])
    if measured_stages == {"music_features_extraction"}:
        lines.append(
            "We separately measured the lightweight stage of extracting musical features from already obtained MXL/MusicXML files. This is not the time of full OMR recognition and not an evaluation of musical correctness."
        )
    else:
        lines.append(
            "We separate the heavy OMR stage from the lighter stage of extracting musical features from already obtained MXL/MusicXML. A benchmark by pipeline stages was added for this purpose. Binarization is considered not as a mandatory replacement for the original image, but as an additional preprocessing/feature source for routing and as a possible fallback for difficult pages."
        )
    lines.extend(
        [
            "",
            "## Run details",
            "",
            f"- Command: `{command}`",
            f"- Report: `{_relative(args.output)}`",
            f"- Raw CSV: `{_relative(args.raw_output)}`",
        ]
    )
    if "routing_binary_feature_probe" in measured_stages:
        lines.append(f"- Feature probe CSV: `{_relative(args.feature_probe_output)}`")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-size", type=int, default=50)
    parser.add_argument("--doc-id")
    parser.add_argument("--only-existing-omr", action="store_true")
    parser.add_argument("--include-routing", action="store_true", default=True)
    parser.add_argument("--no-routing", dest="include_routing", action="store_false")
    parser.add_argument("--include-music-features", action="store_true", default=True)
    parser.add_argument("--no-music-features", dest="include_music_features", action="store_false")
    parser.add_argument("--include-midi-conversion", action="store_true")
    parser.add_argument("--include-omr-existing-sample", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--raw-output", type=Path)
    parser.add_argument("--feature-probe-output", type=Path, default=DEFAULT_PROBE)
    parser.add_argument("--notes-output", type=Path)
    parser.add_argument("--audiveris-bin", default="audiveris")
    args = parser.parse_args()
    if args.only_existing_omr:
        args.include_routing = False
        args.include_midi_conversion = False
        args.include_omr_existing_sample = False
    if args.raw_output is None:
        if args.output.name == "music_features_timing_report.md":
            args.raw_output = args.output.with_name("music_features_timing_raw.csv")
        else:
            args.raw_output = DEFAULT_RAW
    if args.notes_output is None:
        if args.output.name == "music_features_timing_report.md":
            args.notes_output = (
                PROJECT_ROOT
                / "docs"
                / "thesis"
                / "local_vkr"
                / "music_features_timing_notes.md"
            )
        else:
            args.notes_output = DEFAULT_NOTES
    return args


def main() -> None:
    args = parse_args()
    if args.sample_size <= 0:
        raise SystemExit("--sample-size must be a positive integer")

    page_samples = collect_page_samples(
        sample_size=args.sample_size,
        doc_id=args.doc_id,
    )
    mxl_samples = collect_mxl_samples(
        sample_size=args.sample_size,
        doc_id=args.doc_id,
    )

    if args.dry_run:
        print(f"Pages available for timing: {len(page_samples)}")
        print(f"MXL/MusicXML files available for timing: {len(mxl_samples)}")
        print(f"Audiveris would run: {args.include_omr_existing_sample}")
        print("No benchmark was executed because --dry-run was set.")
        return

    raw_rows: list[dict[str, object]] = []
    probe_rows: list[dict[str, object]] = []

    if args.include_routing and page_samples:
        page_rows, probe_rows = run_page_timing(page_samples)
        raw_rows.extend(page_rows)
        write_csv(args.feature_probe_output, probe_rows, PROBE_COLUMNS)

    if args.include_music_features and mxl_samples:
        raw_rows.extend(run_music_feature_timing(mxl_samples))

    if args.include_midi_conversion and mxl_samples:
        raw_rows.extend(
            run_midi_conversion_timing(
                mxl_samples,
                PROJECT_ROOT / "outputs" / "tmp_benchmark_midi",
            )
        )

    if args.include_omr_existing_sample and page_samples:
        raw_rows.extend(
            run_optional_audiveris_timing(
                page_samples[: min(args.sample_size, 5)],
                PROJECT_ROOT / "outputs" / "tmp_benchmark_omr",
                args.audiveris_bin,
            )
        )

    summary_rows = summarize_stage(raw_rows)
    write_csv(args.raw_output, raw_rows, RAW_COLUMNS)
    write_markdown_report(
        args.output,
        args=args,
        summary_rows=summary_rows,
        raw_path=args.raw_output,
        probe_path=args.feature_probe_output if probe_rows else None,
        page_count=len(page_samples) if args.include_routing else 0,
        mxl_count=len(mxl_samples),
    )
    write_notes(
        args.notes_output,
        args=args,
        summary_rows=summary_rows,
        command=" ".join(sys.argv),
        audiveris_invoked=args.include_omr_existing_sample,
    )

    print(f"Pages measured: {len(page_samples) if args.include_routing else 0}")
    print(f"MXL/MusicXML files measured: {len(mxl_samples)}")
    for row in summary_rows:
        print(
            f"{row['stage']}: count={row['count']} "
            f"mean={row['mean_ms']} ms median={row['median_ms']} ms"
        )
    print(f"Report: {args.output}")
    print(f"Raw CSV: {args.raw_output}")
    if probe_rows:
        print(f"Feature probe CSV: {args.feature_probe_output}")
    print(f"Notes: {args.notes_output}")


if __name__ == "__main__":
    main()
