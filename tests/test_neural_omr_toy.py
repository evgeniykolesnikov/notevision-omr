"""Tests for the experimental toy neural OMR prototype."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def load_script(name: str):
    path = PROJECT_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NeuralOmrToyTests(unittest.TestCase):
    def test_vocab_encode_decode(self) -> None:
        from notevision.experimental.neural_omr.tokenizer import Vocab

        vocab = Vocab(["KEY_0", "TIME_4_4", "NOTE_C4_Q"])
        encoded = vocab.encode(["KEY_0", "TIME_4_4", "NOTE_C4_Q"], max_length=8)
        self.assertEqual(vocab.decode(encoded), ["KEY_0", "TIME_4_4", "NOTE_C4_Q"])

    def test_tokenizer_simple_musicxml(self) -> None:
        from notevision.experimental.neural_omr.tokenizer import tokenize_musicxml

        musicxml = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list><score-part id="P1"><part-name>Music</part-name></score-part></part-list>
  <part id="P1"><measure number="1">
    <attributes><divisions>1</divisions><key><fifths>0</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>
    <note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration><type>quarter</type></note>
  </measure></part>
</score-partwise>"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.musicxml"
            path.write_text(musicxml, encoding="utf-8")
            result = tokenize_musicxml(path)
        self.assertIn("KEY_0", result.tokens)
        self.assertIn("TIME_4_4", result.tokens)
        self.assertTrue(any(token.startswith("NOTE_C4") for token in result.tokens))

    def test_model_forward_if_torch_available(self) -> None:
        try:
            import torch
        except Exception as error:  # pragma: no cover - environment dependent
            self.skipTest(f"torch is not available in this environment: {error}")
        from notevision.experimental.neural_omr.model import ModelConfig, create_model

        model = create_model(ModelConfig(vocab_size=12, sequence_length=8, image_size=32))
        output = model(torch.zeros(2, 1, 32, 32))
        self.assertEqual(tuple(output.shape), (2, 8, 12))

    def test_train_and_evaluate_scripts_import(self) -> None:
        self.assertTrue(hasattr(load_script("train_neural_omr_toy"), "train"))
        self.assertTrue(hasattr(load_script("evaluate_neural_omr_toy"), "evaluate"))

    def test_token_accuracy(self) -> None:
        module = load_script("evaluate_neural_omr_toy")
        self.assertEqual(module.token_accuracy(["A", "B"], ["A", "C"]), 0.5)


if __name__ == "__main__":
    unittest.main()
