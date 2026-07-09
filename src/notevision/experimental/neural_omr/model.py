"""Small PyTorch model for toy neural OMR token prediction."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ModelConfig:
    vocab_size: int
    sequence_length: int = 64
    image_size: int = 224
    hidden_dim: int = 128


def get_device(prefer_cuda: bool = True) -> str:
    import torch

    return "cuda" if prefer_cuda and torch.cuda.is_available() else "cpu"


def create_model(config: ModelConfig):
    import torch
    from torch import nn

    class ToyNeuralOmrModel(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.encoder = nn.Sequential(
                nn.Conv2d(1, 16, kernel_size=5, stride=2, padding=2),
                nn.ReLU(inplace=True),
                nn.MaxPool2d(2),
                nn.Conv2d(16, 32, kernel_size=3, stride=2, padding=1),
                nn.ReLU(inplace=True),
                nn.MaxPool2d(2),
                nn.Conv2d(32, 64, kernel_size=3, stride=2, padding=1),
                nn.ReLU(inplace=True),
                nn.AdaptiveAvgPool2d((1, 1)),
                nn.Flatten(),
            )
            self.head = nn.Sequential(
                nn.Linear(64, config.hidden_dim),
                nn.ReLU(inplace=True),
                nn.Linear(config.hidden_dim, config.sequence_length * config.vocab_size),
            )

        def forward(self, images):
            batch = images.shape[0]
            features = self.encoder(images)
            logits = self.head(features)
            return logits.view(batch, config.sequence_length, config.vocab_size)

    return ToyNeuralOmrModel()


def load_checkpoint(path, map_location="cpu"):
    import torch

    return torch.load(path, map_location=map_location)
