"""Compare toy neural inference runtime with Audiveris timing sample."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
for import_path in (PROJECT_ROOT, SRC_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from notevision.experimental.neural_omr.model import ModelConfig, create_model, get_device  # noqa: E402
from notevision.experimental.neural_omr.tokenizer import Vocab  # noqa: E402
from scripts.train_neural_omr_toy import load_image_tensor, read_csv, resolve_project_path, write_csv  # noqa: E402

DEFAULT_MODEL_DIR = PROJECT_ROOT / "outputs" / "experiments" / "neural_omr_toy"
DEFAULT_SAMPLE = PROJECT_ROOT / "outputs" / "reports" / "omr_timing_sample_pages.csv"
DEFAULT_AUDIVERIS_RAW = PROJECT_ROOT / "outputs" / "reports" / "omr_timing_sample_raw.csv"
DEFAULT_SAMPLE_OUT = PROJECT_ROOT / "outputs" / "reports" / "neural_vs_audiveris_timing_sample.csv"
DEFAULT_RAW = PROJECT_ROOT / "outputs" / "reports" / "neural_vs_audiveris_timing_raw.csv"
DEFAULT_REPORT = PROJECT_ROOT / "outputs" / "reports" / "neural_vs_audiveris_timing_report.md"
DEFAULT_NOTES = PROJECT_ROOT / "docs" / "thesis" / "local_vkr" / "neural_vs_audiveris_timing_notes.md"

RAW_COLUMNS = [
    "doc_id",
    "page_index",
    "page_type",
    "png_path",
    "mxl_path",
    "image_load_ms",
    "preprocessing_ms",
    "neural_inference_ms",
    "decoding_ms",
    "total_neural_ms",
    "neural_cpu_inference_ms",
    "neural_cuda_inference_ms",
    "cuda_speedup",
    "predicted_token_count",
    "device",
    "audiveris_omr_ms",
    "midi_conversion_ms",
    "music_features_extraction_ms",
    "total_audiveris_pipeline_ms",
    "mxl_created",
    "midi_created",
    "features_extracted",
    "error",
]


def mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def median(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


def load_model(model_dir: Path):
    import torch

    checkpoint_path = model_dir / "model.pt"
    vocab_path = model_dir / "vocab.json"
    if not checkpoint_path.is_file() or not vocab_path.is_file():
        return None, None, None, "model.pt or vocab.json is missing"
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    vocab = Vocab.load(vocab_path)
    config = checkpoint["config"]
    device = get_device()
    model = create_model(ModelConfig(config["vocab_size"], config["sequence_length"], config["image_size"])).to(device)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    return model, vocab, config, ""


def build_sample(sample_path: Path, audiveris_raw: Path, output_path: Path) -> list[dict[str, str]]:
    audiveris_rows = read_csv(audiveris_raw) if audiveris_raw.exists() else []
    mxl_lookup = {(row["doc_id"], row["page_index"]): row.get("mxl_path", "") for row in audiveris_rows}
    rows = []
    for row in read_csv(sample_path):
        rows.append(
            {
                "doc_id": row["doc_id"],
                "page_index": row["page_index"],
                "page_type": row["page_type"],
                "png_path": row["png_path"],
                "mxl_path": mxl_lookup.get((row["doc_id"], row["page_index"]), ""),
                "selected_for_comparison": 1,
            }
        )
    write_csv(output_path, rows, ["doc_id", "page_index", "page_type", "png_path", "mxl_path", "selected_for_comparison"])
    return rows


def compare(args: argparse.Namespace) -> dict[str, object]:
    import torch

    model, vocab, config, model_error = load_model(args.model_dir)
    sample_rows = build_sample(args.sample, args.audiveris_raw, args.sample_out)
    audiveris_rows = {(row["doc_id"], row["page_index"]): row for row in read_csv(args.audiveris_raw)} if args.audiveris_raw.exists() else {}
    raw_rows: list[dict[str, object]] = []
    if model_error:
        for row in sample_rows:
            raw_rows.append({**row, "error": model_error})
        write_csv(args.raw, raw_rows, RAW_COLUMNS)
        summary = {"comparison_possible": False, "reason": model_error}
        write_report(args.report, summary)
        write_notes(args.notes, summary)
        return summary
    assert model is not None and vocab is not None and config is not None
    device = get_device()
    cpu_model = None
    if device == "cuda":
        checkpoint = torch.load(args.model_dir / "model.pt", map_location="cpu")
        cpu_model = create_model(ModelConfig(config["vocab_size"], config["sequence_length"], config["image_size"]))
        cpu_model.load_state_dict(checkpoint["model_state_dict"])
        cpu_model.eval()
    for row in sample_rows:
        error = ""
        start_total = time.perf_counter()
        start = time.perf_counter()
        image_path = resolve_project_path(row["png_path"])
        try:
            image = load_image_tensor(image_path, int(config["image_size"]))
        except Exception as exc:
            image = None
            error = f"image_load_error: {exc}"
        image_load_ms = (time.perf_counter() - start) * 1000.0
        preprocessing_ms = 0.0
        inference_ms = 0.0
        cpu_inference_ms = 0.0
        cuda_inference_ms = 0.0
        decoding_ms = 0.0
        predicted_count = 0
        if image is not None:
            if cpu_model is not None:
                cpu_image = image.unsqueeze(0)
                start = time.perf_counter()
                with torch.no_grad():
                    _ = cpu_model(cpu_image)
                cpu_inference_ms = (time.perf_counter() - start) * 1000.0
            image = image.unsqueeze(0).to(device)
            start = time.perf_counter()
            if device == "cuda":
                torch.cuda.synchronize()
            preprocessing_ms = (time.perf_counter() - start) * 1000.0
            start = time.perf_counter()
            with torch.no_grad():
                logits = model(image)
            if device == "cuda":
                torch.cuda.synchronize()
            inference_ms = (time.perf_counter() - start) * 1000.0
            if device == "cuda":
                cuda_inference_ms = inference_ms
            else:
                cpu_inference_ms = inference_ms
            start = time.perf_counter()
            predicted = vocab.decode(logits.argmax(dim=-1).squeeze(0).cpu().tolist())
            predicted_count = len(predicted)
            decoding_ms = (time.perf_counter() - start) * 1000.0
        total_neural = (time.perf_counter() - start_total) * 1000.0
        aud = audiveris_rows.get((row["doc_id"], row["page_index"]), {})
        raw_rows.append(
            {
                **row,
                "image_load_ms": round(image_load_ms, 3),
                "preprocessing_ms": round(preprocessing_ms, 3),
                "neural_inference_ms": round(inference_ms, 3),
                "decoding_ms": round(decoding_ms, 3),
                "total_neural_ms": round(total_neural, 3),
                "neural_cpu_inference_ms": round(cpu_inference_ms, 3),
                "neural_cuda_inference_ms": round(cuda_inference_ms, 3),
                "cuda_speedup": round(cpu_inference_ms / cuda_inference_ms, 3) if cuda_inference_ms else "",
                "predicted_token_count": predicted_count,
                "device": device,
                "audiveris_omr_ms": aud.get("audiveris_omr_ms", ""),
                "midi_conversion_ms": aud.get("midi_conversion_ms", ""),
                "music_features_extraction_ms": aud.get("music_features_extraction_ms", ""),
                "total_audiveris_pipeline_ms": aud.get("total_ms", ""),
                "mxl_created": aud.get("mxl_created", ""),
                "midi_created": aud.get("midi_created", ""),
                "features_extracted": aud.get("features_extracted", ""),
                "error": error,
            }
        )
    write_csv(args.raw, raw_rows, RAW_COLUMNS)
    neural_values = [float(row["total_neural_ms"]) for row in raw_rows if not str(row["error"]).strip()]
    cpu_values = [float(row["neural_cpu_inference_ms"]) for row in raw_rows if str(row["neural_cpu_inference_ms"]).strip() and float(row["neural_cpu_inference_ms"]) > 0]
    cuda_values = [float(row["neural_cuda_inference_ms"]) for row in raw_rows if str(row["neural_cuda_inference_ms"]).strip() and float(row["neural_cuda_inference_ms"]) > 0]
    aud_total = [float(row["total_audiveris_pipeline_ms"]) for row in raw_rows if str(row["total_audiveris_pipeline_ms"]).strip()]
    aud_omr = [float(row["audiveris_omr_ms"]) for row in raw_rows if str(row["audiveris_omr_ms"]).strip()]
    summary = {
        "comparison_possible": True,
        "pages_compared": len(raw_rows),
        "neural_device": device,
        "mean_neural_total_ms": mean(neural_values),
        "median_neural_total_ms": median(neural_values),
        "mean_audiveris_total_ms": mean(aud_total),
        "median_audiveris_total_ms": median(aud_total),
        "mean_audiveris_omr_ms": mean(aud_omr),
        "speedup_by_total_time": mean(aud_total) / mean(neural_values) if mean(neural_values) else 0.0,
        "speedup_by_omr_stage": mean(aud_omr) / mean(neural_values) if mean(neural_values) else 0.0,
        "mean_neural_cpu_inference_ms": mean(cpu_values),
        "mean_neural_cuda_inference_ms": mean(cuda_values),
        "cuda_speedup": mean(cpu_values) / mean(cuda_values) if mean(cuda_values) else 0.0,
    }
    write_report(args.report, summary)
    write_notes(args.notes, summary)
    update_neural_notes(args.notes)
    return summary


def write_report(path: Path, summary: dict[str, object]) -> None:
    lines = ["# Neural vs Audiveris timing report", ""]
    if not summary.get("comparison_possible"):
        lines.extend(["Comparison was not possible.", f"- reason: {summary.get('reason')}", ""])
    else:
        lines.extend(
            [
                "| metric | value |",
                "|---|---:|",
                f"| pages_compared | {summary['pages_compared']} |",
                f"| neural_device | {summary['neural_device']} |",
                f"| mean_neural_total_ms | {float(summary['mean_neural_total_ms']):.3f} |",
                f"| median_neural_total_ms | {float(summary['median_neural_total_ms']):.3f} |",
                f"| mean_audiveris_total_ms | {float(summary['mean_audiveris_total_ms']):.3f} |",
                f"| median_audiveris_total_ms | {float(summary['median_audiveris_total_ms']):.3f} |",
                f"| mean_audiveris_omr_ms | {float(summary['mean_audiveris_omr_ms']):.3f} |",
                f"| speedup_by_total_time | {float(summary['speedup_by_total_time']):.2f} |",
                f"| speedup_by_omr_stage | {float(summary['speedup_by_omr_stage']):.2f} |",
                f"| mean_neural_cpu_inference_ms | {float(summary.get('mean_neural_cpu_inference_ms', 0.0)):.3f} |",
                f"| mean_neural_cuda_inference_ms | {float(summary.get('mean_neural_cuda_inference_ms', 0.0)):.3f} |",
                f"| cuda_speedup | {float(summary.get('cuda_speedup', 0.0)):.2f} |",
                "",
                "This is runtime speedup on a simplified toy task, not evidence that the prototype replaces Audiveris.",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_notes(path: Path, summary: dict[str, object]) -> None:
    lines = [
        "# neural_vs_audiveris_timing_notes",
        "",
        "DOCX VKR, defense PPTX/PDF, the main pipeline and final VKR metrics were not changed. Git was not touched.",
        "",
    ]
    if summary.get("comparison_possible"):
        lines.extend(
            [
                f"- pages_compared: {summary['pages_compared']}",
                f"- neural_device: {summary['neural_device']}",
                f"- mean_neural_total_ms: {float(summary['mean_neural_total_ms']):.3f}",
                f"- mean_audiveris_total_ms: {float(summary['mean_audiveris_total_ms']):.3f}",
                f"- mean_audiveris_omr_ms: {float(summary['mean_audiveris_omr_ms']):.3f}",
                f"- speedup_by_total_time: {float(summary['speedup_by_total_time']):.2f}",
                f"- mean_neural_cpu_inference_ms: {float(summary.get('mean_neural_cpu_inference_ms', 0.0)):.3f}",
                f"- mean_neural_cuda_inference_ms: {float(summary.get('mean_neural_cuda_inference_ms', 0.0)):.3f}",
                f"- cuda_speedup: {float(summary.get('cuda_speedup', 0.0)):.2f}",
                "",
            ]
        )
    else:
        lines.append(f"- comparison_not_possible_reason: {summary.get('reason')}")
    lines.extend(
        [
            "## Defense wording",
            "",
            "Audiveris and the experimental neural OMR model solve tasks of different completeness. Audiveris builds full MXL/MusicXML, while the toy neural prototype predicts a simplified token sequence. Therefore this is only a runtime comparison and an illustration of possible GPU-oriented development. It does not prove musical correctness and does not replace final VKR metrics.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def update_neural_notes(timing_notes: Path) -> None:
    path = PROJECT_ROOT / "docs" / "thesis" / "local_vkr" / "neural_omr_experiment_notes.md"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    marker = "## Runtime comparison with Audiveris"
    addition = f"\n{marker}\n\nSee `{timing_notes.relative_to(PROJECT_ROOT)}`. This comparison is runtime-only and does not compare OMR quality.\n"
    if marker not in text:
        path.write_text(text.rstrip() + "\n" + addition, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--audiveris-raw", type=Path, default=DEFAULT_AUDIVERIS_RAW)
    parser.add_argument("--sample-out", type=Path, default=DEFAULT_SAMPLE_OUT)
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--notes", type=Path, default=DEFAULT_NOTES)
    return parser.parse_args()


def main() -> int:
    print(json.dumps(compare(parse_args()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
