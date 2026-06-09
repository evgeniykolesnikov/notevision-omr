"""Optional PyTorch MobileNetV3 baseline with conservative augmentations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .classical import classification_metrics
from .dataset import PageRecord

AUGMENTATION_DESCRIPTION = (
    "resize/crop; rotation ±3 degrees; brightness/contrast jitter; "
    "light Gaussian blur; no flips or perspective transforms"
)


def require_torch() -> tuple[Any, Any, Any, Any, Any]:
    try:
        import torch
        from PIL import Image
        from torch import nn
        from torch.utils.data import DataLoader, Dataset
        from torchvision import models, transforms
    except (ImportError, OSError) as error:
        raise RuntimeError(
            "CNN training requires compatible torch and torchvision packages."
        ) from error
    return torch, nn, DataLoader, Dataset, (Image, models, transforms)


def build_transforms(*, training: bool, image_size: int = 224) -> Any:
    _, _, _, _, modules = require_torch()
    _, _, transforms = modules
    if training:
        return transforms.Compose(
            [
                transforms.RandomResizedCrop(
                    image_size, scale=(0.9, 1.0), ratio=(0.96, 1.04)
                ),
                transforms.RandomRotation(3, fill=255),
                transforms.ColorJitter(brightness=0.15, contrast=0.15),
                transforms.RandomApply(
                    [transforms.GaussianBlur(kernel_size=3, sigma=(0.1, 0.8))],
                    p=0.2,
                ),
                transforms.Grayscale(num_output_channels=3),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=(0.485, 0.456, 0.406),
                    std=(0.229, 0.224, 0.225),
                ),
            ]
        )
    return transforms.Compose(
        [
            transforms.Resize((image_size, image_size)),
            transforms.Grayscale(num_output_channels=3),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=(0.485, 0.456, 0.406),
                std=(0.229, 0.224, 0.225),
            ),
        ]
    )


def build_mobilenet(num_classes: int, *, pretrained: bool = True) -> tuple[Any, bool]:
    _, nn, _, _, modules = require_torch()
    _, models, _ = modules
    pretrained_loaded = False
    if pretrained:
        try:
            model = models.mobilenet_v3_small(
                weights=models.MobileNet_V3_Small_Weights.DEFAULT
            )
            pretrained_loaded = True
        except Exception:
            model = models.mobilenet_v3_small(weights=None)
    else:
        model = models.mobilenet_v3_small(weights=None)
    input_features = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(input_features, num_classes)
    return model, pretrained_loaded


def _dataset_class() -> type:
    _, _, _, Dataset, modules = require_torch()
    Image, _, _ = modules

    class PageImageDataset(Dataset):
        def __init__(
            self,
            records: list[PageRecord],
            class_to_index: dict[int | str, int],
            transform: Any,
        ) -> None:
            self.records = records
            self.class_to_index = class_to_index
            self.transform = transform

        def __len__(self) -> int:
            return len(self.records)

        def __getitem__(self, index: int) -> tuple[Any, int]:
            record = self.records[index]
            with Image.open(record.image_path) as image:
                tensor = self.transform(image.convert("RGB"))
            return tensor, self.class_to_index.get(record.target, 0)

    return PageImageDataset


def filter_readable_records(
    records: list[PageRecord],
) -> tuple[list[PageRecord], list[dict[str, str]]]:
    """Validate images before DataLoader workers see them."""
    _, _, _, _, modules = require_torch()
    Image, _, _ = modules
    valid = []
    errors = []
    for record in records:
        try:
            with Image.open(record.image_path) as image:
                image.verify()
        except (FileNotFoundError, OSError, ValueError) as error:
            errors.append(
                {
                    "doc_id": record.doc_id,
                    "page_index": str(record.page_index),
                    "image_path": str(record.image_path),
                    "error": str(error),
                }
            )
            continue
        valid.append(record)
    return valid, errors


def train_cnn(
    train_records: list[PageRecord],
    validation_records: list[PageRecord],
    *,
    model_path: Path,
    target: str,
    epochs: int = 30,
    batch_size: int = 16,
    patience: int = 5,
    pretrained: bool = True,
) -> dict[str, object]:
    """Train MobileNetV3 Small and stop when validation F1 stops improving."""
    torch, nn, DataLoader, _, _ = require_torch()
    classes = sorted(
        {record.target for record in train_records + validation_records},
        key=str,
    )
    if len(classes) < 2:
        raise ValueError("CNN training requires at least two target classes")
    class_to_index = {label: index for index, label in enumerate(classes)}
    DatasetClass = _dataset_class()
    train_dataset = DatasetClass(
        train_records, class_to_index, build_transforms(training=True)
    )
    validation_dataset = DatasetClass(
        validation_records, class_to_index, build_transforms(training=False)
    )
    train_loader = DataLoader(
        train_dataset, batch_size=batch_size, shuffle=True, num_workers=0
    )
    validation_loader = DataLoader(
        validation_dataset, batch_size=batch_size, shuffle=False, num_workers=0
    )
    model, pretrained_loaded = build_mobilenet(
        len(classes), pretrained=pretrained
    )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
    criterion = nn.CrossEntropyLoss()
    best_state = None
    best_metrics: dict[str, object] | None = None
    best_epoch = 0
    stale_epochs = 0

    for epoch in range(1, epochs + 1):
        model.train()
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            loss = criterion(model(images), labels)
            loss.backward()
            optimizer.step()

        model.eval()
        truth: list[int | str] = []
        predictions: list[int | str] = []
        with torch.no_grad():
            for images, labels in validation_loader:
                logits = model(images.to(device))
                predicted = logits.argmax(dim=1).cpu().tolist()
                truth.extend(classes[index] for index in labels.tolist())
                predictions.extend(classes[index] for index in predicted)
        metrics = classification_metrics(truth, predictions)
        if best_metrics is None or float(metrics["f1"]) > float(best_metrics["f1"]):
            best_metrics = metrics
            best_epoch = epoch
            best_state = {
                key: value.detach().cpu()
                for key, value in model.state_dict().items()
            }
            stale_epochs = 0
        else:
            stale_epochs += 1
            if stale_epochs >= patience:
                break

    if best_state is None or best_metrics is None:
        raise RuntimeError("CNN training did not produce a validation result")
    model_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "kind": "cnn",
            "architecture": "mobilenet_v3_small",
            "target": target,
            "classes": classes,
            "state_dict": best_state,
            "pretrained_loaded": pretrained_loaded,
            "augmentations": AUGMENTATION_DESCRIPTION,
        },
        model_path,
    )
    return {
        "model_path": model_path,
        "metrics": best_metrics,
        "epochs_requested": epochs,
        "best_epoch": best_epoch,
        "pretrained_loaded": pretrained_loaded,
        "augmentations": AUGMENTATION_DESCRIPTION,
    }


def predict_cnn(model_path: Path, records: list[PageRecord]) -> list[dict[str, object]]:
    torch, _, _, _, modules = require_torch()
    Image, _, _ = modules
    payload = torch.load(model_path, map_location="cpu")
    classes = list(payload["classes"])
    model, _ = build_mobilenet(len(classes), pretrained=False)
    model.load_state_dict(payload["state_dict"])
    model.eval()
    transform = build_transforms(training=False)
    rows = []
    with torch.no_grad():
        for record in records:
            try:
                with Image.open(record.image_path) as image:
                    tensor = transform(image.convert("RGB")).unsqueeze(0)
                probabilities = torch.softmax(model(tensor), dim=1)[0]
                score, index = probabilities.max(dim=0)
                rows.append(
                    {
                        "doc_id": record.doc_id,
                        "page_index": record.page_index,
                        "image_path": str(record.image_path),
                        "prediction": classes[int(index.item())],
                        "score": float(score.item()),
                        "status": "success",
                        "error": "",
                    }
                )
            except (FileNotFoundError, OSError, ValueError) as error:
                rows.append(
                    {
                        "doc_id": record.doc_id,
                        "page_index": record.page_index,
                        "image_path": str(record.image_path),
                        "prediction": "",
                        "score": "",
                        "status": "failed",
                        "error": str(error),
                    }
                )
    return rows
