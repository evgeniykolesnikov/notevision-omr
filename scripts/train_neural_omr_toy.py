"""Train a toy neural OMR proof-of-concept on pseudo-label tokens."""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
for import_path in (PROJECT_ROOT, SRC_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from scripts.analyze_music_features_unique_pages import find_related_midi  # noqa: E402
from notevision.experimental.neural_omr.model import ModelConfig, create_model, get_device  # noqa: E402
from notevision.experimental.neural_omr.tokenizer import DEFAULT_MAX_TOKENS, Vocab, build_vocab, tokenize_musicxml  # noqa: E402

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "experiments" / "neural_omr_toy"
DEFAULT_UNIQUE_PAGES = PROJECT_ROOT / "outputs" / "reports" / "music_features_by_unique_page.csv"

PAIR_COLUMNS = [
    "doc_id",
    "page_index",
    "png_path",
    "mxl_path",
    "midi_exists",
    "source_variant",
    "parse_status",
    "token_sequence",
    "token_count",
    "warning",
]


def resolve_project_path(value: object) -> Path:
    raw = str(value or "").strip().replace("\\", "/")
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except (OSError, ValueError):
        return str(path)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def write_csv(path: Path, rows: list[dict[str, object]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_pairs(unique_pages_csv: Path, output_dir: Path, max_tokens: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    validated_by_key = {}
    labels_path = PROJECT_ROOT / "data" / "labels" / "pages_validated_thesis.csv"
    if labels_path.exists():
        for item in read_csv(labels_path):
            validated_by_key[(str(item.get("doc_id")), str(int(float(item.get("page_index", "0")))))] = item
    for row in read_csv(unique_pages_csv):
        if str(row.get("mxl_exists")) != "1":
            continue
        if str(row.get("extraction_status")) in {"failed", "no_mxl"}:
            continue
        doc_id = str(row["doc_id"])
        page_index = str(row["page_index"])
        label = validated_by_key.get((doc_id, page_index), {})
        png_path = resolve_project_path(label.get("image_path", ""))
        mxl_path = resolve_project_path(row.get("selected_mxl_path", ""))
        if not png_path.is_file() or not mxl_path.is_file():
            continue
        result = tokenize_musicxml(mxl_path, max_events=max_tokens - 8)
        if not result.tokens:
            continue
        warning = result.warning
        tokens = result.tokens[:max_tokens]
        if len(result.tokens) > max_tokens:
            warning = "truncated"
        rows.append(
            {
                "doc_id": doc_id,
                "page_index": page_index,
                "png_path": rel(png_path),
                "mxl_path": rel(mxl_path),
                "midi_exists": int(find_related_midi(doc_id, page_index)),
                "source_variant": row.get("selected_variant", ""),
                "parse_status": "ok",
                "token_sequence": " ".join(tokens),
                "token_count": len(tokens),
                "warning": warning,
            }
        )
    write_csv(output_dir / "neural_omr_pairs.csv", rows, PAIR_COLUMNS)
    return rows


def split_by_doc(rows: list[dict[str, object]], output_dir: Path, seed: int = 42) -> list[dict[str, object]]:
    docs = sorted({str(row["doc_id"]) for row in rows})
    random.Random(seed).shuffle(docs)
    val_count = max(1, int(round(len(docs) * 0.2))) if len(docs) > 1 else 0
    val_docs = set(docs[:val_count])
    split_rows: list[dict[str, object]] = []
    for row in rows:
        split_rows.append(
            {
                "doc_id": row["doc_id"],
                "page_index": row["page_index"],
                "split": "val" if str(row["doc_id"]) in val_docs else "train",
            }
        )
    write_csv(output_dir / "split.csv", split_rows, ["doc_id", "page_index", "split"])
    return split_rows


def load_image_tensor(path: Path, image_size: int):
    import torch
    from PIL import Image

    with Image.open(path) as image:
        image = image.convert("L").resize((image_size, image_size))
        data = torch.tensor(list(image.tobytes()), dtype=torch.float32)
    return data.view(1, image_size, image_size) / 255.0


class ToyDataset:
    def __init__(self, rows: list[dict[str, object]], vocab: Vocab, image_size: int, sequence_length: int) -> None:
        self.rows = rows
        self.vocab = vocab
        self.image_size = image_size
        self.sequence_length = sequence_length

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int):
        import torch

        row = self.rows[index]
        image = load_image_tensor(resolve_project_path(row["png_path"]), self.image_size)
        tokens = str(row["token_sequence"]).split()
        target = torch.tensor(self.vocab.encode(tokens, self.sequence_length), dtype=torch.long)
        return image, target


def batch_iter(dataset: ToyDataset, batch_size: int, shuffle: bool = True):
    import torch

    indices = list(range(len(dataset)))
    if shuffle:
        random.shuffle(indices)
    for start in range(0, len(indices), batch_size):
        batch_indices = indices[start : start + batch_size]
        images, targets = zip(*(dataset[index] for index in batch_indices))
        yield torch.stack(images), torch.stack(targets)


def evaluate_model(model, dataset: ToyDataset, device: str, batch_size: int) -> dict[str, float]:
    import torch
    from torch import nn

    if len(dataset) == 0:
        return {"loss": 0.0, "token_accuracy": 0.0, "sequence_exact_match": 0.0, "inference_time_ms": 0.0}
    criterion = nn.CrossEntropyLoss(ignore_index=dataset.vocab.pad_id)
    total_loss = 0.0
    total_tokens = 0
    correct_tokens = 0
    exact = 0
    timings: list[float] = []
    model.eval()
    with torch.no_grad():
        for images, targets in batch_iter(dataset, batch_size, shuffle=False):
            images = images.to(device)
            targets = targets.to(device)
            start = time.perf_counter()
            logits = model(images)
            if device == "cuda":
                torch.cuda.synchronize()
            timings.append((time.perf_counter() - start) * 1000.0 / max(1, images.shape[0]))
            loss = criterion(logits.reshape(-1, logits.shape[-1]), targets.reshape(-1))
            total_loss += float(loss.item()) * images.shape[0]
            preds = logits.argmax(dim=-1)
            mask = targets != dataset.vocab.pad_id
            total_tokens += int(mask.sum().item())
            correct_tokens += int(((preds == targets) & mask).sum().item())
            exact += int((((preds == targets) | ~mask).all(dim=1)).sum().item())
    return {
        "loss": total_loss / len(dataset),
        "token_accuracy": correct_tokens / total_tokens if total_tokens else 0.0,
        "sequence_exact_match": exact / len(dataset),
        "inference_time_ms": sum(timings) / len(timings) if timings else 0.0,
    }


def train(args: argparse.Namespace) -> dict[str, object]:
    import torch
    from torch import nn

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    pairs = build_pairs(args.unique_pages_csv, output_dir, args.sequence_length)
    split_rows = split_by_doc(pairs, output_dir)
    split_lookup = {(str(row["doc_id"]), str(row["page_index"])): row["split"] for row in split_rows}
    rows = pairs[: args.max_samples] if args.max_samples else pairs
    token_sequences = [str(row["token_sequence"]).split() for row in rows]
    vocab = build_vocab(token_sequences)
    vocab.save(output_dir / "vocab.json")
    train_rows = [row for row in rows if split_lookup.get((str(row["doc_id"]), str(row["page_index"]))) == "train"]
    val_rows = [row for row in rows if split_lookup.get((str(row["doc_id"]), str(row["page_index"]))) == "val"]
    if not val_rows and train_rows:
        val_rows = train_rows[-max(1, len(train_rows) // 5) :]
        train_rows = train_rows[: -len(val_rows)] or train_rows

    device = get_device()
    model = create_model(ModelConfig(len(vocab), sequence_length=args.sequence_length, image_size=args.image_size)).to(device)
    criterion = nn.CrossEntropyLoss(ignore_index=vocab.pad_id)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate)
    train_dataset = ToyDataset(train_rows, vocab, args.image_size, args.sequence_length)
    val_dataset = ToyDataset(val_rows, vocab, args.image_size, args.sequence_length)
    log_rows = []
    start_train = time.perf_counter()
    for epoch in range(1, args.epochs + 1):
        model.train()
        epoch_loss = 0.0
        seen = 0
        for images, targets in batch_iter(train_dataset, args.batch_size, shuffle=True):
            images = images.to(device)
            targets = targets.to(device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(images)
            loss = criterion(logits.reshape(-1, logits.shape[-1]), targets.reshape(-1))
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.item()) * images.shape[0]
            seen += images.shape[0]
        val_metrics = evaluate_model(model, val_dataset, device, args.batch_size)
        log_rows.append(
            {
                "epoch": epoch,
                "train_loss": epoch_loss / max(1, seen),
                "val_loss": val_metrics["loss"],
                "token_accuracy": val_metrics["token_accuracy"],
                "sequence_exact_match": val_metrics["sequence_exact_match"],
            }
        )
    training_seconds = time.perf_counter() - start_train
    val_metrics = evaluate_model(model, val_dataset, device, args.batch_size)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "config": {
                "vocab_size": len(vocab),
                "sequence_length": args.sequence_length,
                "image_size": args.image_size,
            },
            "device": device,
        },
        output_dir / "model.pt",
    )
    write_csv(output_dir / "train_log.csv", log_rows, ["epoch", "train_loss", "val_loss", "token_accuracy", "sequence_exact_match"])
    metrics = {
        "pairs_found": len(pairs),
        "dataset_rows_used": len(rows),
        "train_rows": len(train_rows),
        "val_rows": len(val_rows),
        "vocab_size": len(vocab),
        "device": device,
        "epochs": args.epochs,
        "training_seconds": training_seconds,
        "val_loss": val_metrics["loss"],
        "token_accuracy": val_metrics["token_accuracy"],
        "sequence_exact_match": val_metrics["sequence_exact_match"],
        "inference_time_ms": val_metrics["inference_time_ms"],
    }
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--image-size", type=int, default=224)
    parser.add_argument("--max-samples", type=int, default=100)
    parser.add_argument("--sequence-length", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--unique-pages-csv", type=Path, default=DEFAULT_UNIQUE_PAGES)
    return parser.parse_args()


def main() -> int:
    metrics = train(parse_args())
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
