"""Evaluate toy neural OMR model on validation pseudo-labels."""

from __future__ import annotations

import argparse
import csv
import json
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
from scripts.train_neural_omr_toy import ToyDataset, read_csv, resolve_project_path, write_csv  # noqa: E402

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "experiments" / "neural_omr_toy"
DEFAULT_REPORT = PROJECT_ROOT / "outputs" / "reports" / "neural_omr_toy_report.md"
DEFAULT_PREDICTIONS = PROJECT_ROOT / "outputs" / "reports" / "neural_omr_toy_predictions.csv"
DEFAULT_NOTES = PROJECT_ROOT / "docs" / "thesis" / "local_vkr" / "neural_omr_experiment_notes.md"

PREDICTION_COLUMNS = [
    "doc_id",
    "page_index",
    "target_tokens",
    "predicted_tokens",
    "token_accuracy",
    "exact_match",
    "inference_time_ms",
]


def token_accuracy(target: list[str], predicted: list[str]) -> float:
    if not target:
        return 0.0
    matches = sum(1 for left, right in zip(target, predicted) if left == right)
    return matches / len(target)


def evaluate(args: argparse.Namespace) -> dict[str, object]:
    import torch

    checkpoint_path = args.output_dir / "model.pt"
    vocab_path = args.output_dir / "vocab.json"
    if not checkpoint_path.is_file() or not vocab_path.is_file():
        raise FileNotFoundError("model.pt or vocab.json is missing; train the toy model first")
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    vocab = Vocab.load(vocab_path)
    config_data = checkpoint["config"]
    device = get_device()
    model = create_model(
        ModelConfig(
            vocab_size=config_data["vocab_size"],
            sequence_length=config_data["sequence_length"],
            image_size=config_data["image_size"],
        )
    ).to(device)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    metrics_path = args.output_dir / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}
    pairs = read_csv(args.output_dir / "neural_omr_pairs.csv")
    used_count = int(metrics.get("dataset_rows_used", 0) or 0)
    if used_count:
        pairs = pairs[:used_count]
    split_rows = read_csv(args.output_dir / "split.csv")
    split_lookup = {(row["doc_id"], row["page_index"]): row["split"] for row in split_rows}
    val_rows = [row for row in pairs if split_lookup.get((row["doc_id"], row["page_index"])) == "val"]
    if not val_rows and pairs:
        holdout = max(1, len(pairs) // 5)
        val_rows = pairs[-holdout:]
    val_rows = val_rows[: args.max_samples] if args.max_samples else val_rows
    dataset = ToyDataset(val_rows, vocab, config_data["image_size"], config_data["sequence_length"])
    prediction_rows: list[dict[str, object]] = []
    with torch.no_grad():
        for index, row in enumerate(val_rows):
            image, target_ids = dataset[index]
            image = image.unsqueeze(0).to(device)
            if device == "cuda":
                torch.cuda.synchronize()
            start = time.perf_counter()
            logits = model(image)
            if device == "cuda":
                torch.cuda.synchronize()
            inference_ms = (time.perf_counter() - start) * 1000.0
            predicted_ids = logits.argmax(dim=-1).squeeze(0).cpu().tolist()
            target_tokens = str(row["token_sequence"]).split()
            predicted_tokens = vocab.decode(predicted_ids)
            prediction_rows.append(
                {
                    "doc_id": row["doc_id"],
                    "page_index": row["page_index"],
                    "target_tokens": " ".join(target_tokens),
                    "predicted_tokens": " ".join(predicted_tokens),
                    "token_accuracy": token_accuracy(target_tokens, predicted_tokens),
                    "exact_match": int(target_tokens == predicted_tokens),
                    "inference_time_ms": round(inference_ms, 3),
                }
            )
    write_csv(args.predictions, prediction_rows, PREDICTION_COLUMNS)
    mean_inference = sum(float(row["inference_time_ms"]) for row in prediction_rows) / len(prediction_rows) if prediction_rows else 0.0
    mean_token_accuracy = sum(float(row["token_accuracy"]) for row in prediction_rows) / len(prediction_rows) if prediction_rows else 0.0
    exact_match = sum(int(row["exact_match"]) for row in prediction_rows) / len(prediction_rows) if prediction_rows else 0.0
    summary = {
        "device": device,
        "val_pages": len(prediction_rows),
        "mean_token_accuracy": mean_token_accuracy,
        "sequence_exact_match": exact_match,
        "mean_inference_time_ms": mean_inference,
    }
    write_report(args.report, summary, args.predictions)
    write_notes(args.notes, args.output_dir, summary)
    return summary


def write_report(path: Path, summary: dict[str, object], predictions: Path) -> None:
    lines = [
        "# Neural OMR toy report",
        "",
        "- Scope: experimental proof-of-concept on pseudo-labels from existing MXL/MusicXML.",
        "- This is not a replacement for Audiveris and not a final VKR metric.",
        "",
        "| metric | value |",
        "|---|---:|",
        f"| val_pages | {summary['val_pages']} |",
        f"| device | {summary['device']} |",
        f"| mean_token_accuracy | {float(summary['mean_token_accuracy']):.4f} |",
        f"| sequence_exact_match | {float(summary['sequence_exact_match']):.4f} |",
        f"| mean_inference_time_ms | {float(summary['mean_inference_time_ms']):.3f} |",
        "",
        f"- Predictions: `{predictions.relative_to(PROJECT_ROOT)}`",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_notes(path: Path, output_dir: Path, summary: dict[str, object]) -> None:
    metrics_path = output_dir / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}
    lines = [
        "# neural_omr_experiment_notes",
        "",
        "DOCX VKR, defense PPTX/PDF, the main pipeline and final VKR metrics were not changed. Git was not touched.",
        "",
        "## Status",
        "",
        "- This is an experimental proof-of-concept.",
        "- It is not a replacement for Audiveris.",
        "- It is not a final VKR metric.",
        "- Training uses pseudo-labels from existing MXL/MusicXML.",
        "- Existing MXL/MusicXML are not expert ground truth.",
        "- The model does not guarantee musical correctness.",
        "- CUDA is used only if available.",
        "- Full neural OMR would require expert-verified image-to-MusicXML pairs.",
        "- The main VKR pipeline remains Audiveris baseline.",
        "",
        "## Results",
        "",
        f"- pairs_found: {metrics.get('pairs_found', 'unknown')}",
        f"- dataset_rows_used: {metrics.get('dataset_rows_used', 'unknown')}",
        f"- device: {summary.get('device')}",
        f"- val_pages: {summary.get('val_pages')}",
        f"- mean_token_accuracy: {float(summary.get('mean_token_accuracy', 0.0)):.4f}",
        f"- sequence_exact_match: {float(summary.get('sequence_exact_match', 0.0)):.4f}",
        f"- mean_inference_time_ms: {float(summary.get('mean_inference_time_ms', 0.0)):.3f}",
        "",
        "## Defense wording",
        "",
        "As a future direction, CPU-based Audiveris could be complemented by neural OMR that can use GPU inference. In this project it is only an experimental proof-of-concept, because there is no expert-verified MusicXML ground truth. The prototype is trained on pseudo-labels from already obtained MXL/MusicXML and is not used in final VKR metrics.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--notes", type=Path, default=DEFAULT_NOTES)
    parser.add_argument("--max-samples", type=int, default=100)
    return parser.parse_args()


def main() -> int:
    print(json.dumps(evaluate(parse_args()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
