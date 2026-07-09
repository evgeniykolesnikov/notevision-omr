"""Simplified tokenization for toy neural OMR pseudo-labels."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SPECIAL_TOKENS = ["<pad>", "<bos>", "<eos>", "<unk>"]
DEFAULT_MAX_TOKENS = 64


@dataclass
class TokenizationResult:
    tokens: list[str]
    warning: str = ""


class Vocab:
    def __init__(self, tokens: Iterable[str] | None = None) -> None:
        ordered = list(SPECIAL_TOKENS)
        for token in tokens or []:
            if token not in ordered:
                ordered.append(token)
        self.token_to_id = {token: index for index, token in enumerate(ordered)}
        self.id_to_token = {index: token for token, index in self.token_to_id.items()}

    @property
    def pad_id(self) -> int:
        return self.token_to_id["<pad>"]

    @property
    def bos_id(self) -> int:
        return self.token_to_id["<bos>"]

    @property
    def eos_id(self) -> int:
        return self.token_to_id["<eos>"]

    @property
    def unk_id(self) -> int:
        return self.token_to_id["<unk>"]

    def __len__(self) -> int:
        return len(self.token_to_id)

    def encode(self, tokens: list[str], max_length: int = DEFAULT_MAX_TOKENS) -> list[int]:
        ids = [self.bos_id]
        ids.extend(self.token_to_id.get(token, self.unk_id) for token in tokens[: max_length - 2])
        ids.append(self.eos_id)
        ids = ids[:max_length]
        ids.extend([self.pad_id] * (max_length - len(ids)))
        return ids

    def decode(self, ids: Iterable[int]) -> list[str]:
        tokens: list[str] = []
        for value in ids:
            token = self.id_to_token.get(int(value), "<unk>")
            if token == "<eos>":
                break
            if token not in {"<pad>", "<bos>"}:
                tokens.append(token)
        return tokens

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"tokens": list(self.token_to_id)}, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Vocab":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(data.get("tokens", []))


def normalize_duration(quarter_length: object) -> str:
    try:
        value = float(quarter_length)
    except (TypeError, ValueError):
        return "UNK"
    if value <= 0.5:
        return "E"
    if value <= 1.0:
        return "Q"
    if value <= 2.0:
        return "H"
    return "W"


def key_token(fifths: object) -> str:
    try:
        value = int(float(str(fifths)))
    except (TypeError, ValueError):
        return "KEY_UNKNOWN"
    if -7 <= value <= 7:
        return f"KEY_{value}"
    return "KEY_UNKNOWN"


def time_token(ratio: object) -> str:
    text = str(ratio or "").strip().replace("/", "_")
    if text in {"4_4", "3_4", "2_4", "6_8"}:
        return f"TIME_{text}"
    return "TIME_UNKNOWN"


def clef_token(clef: object) -> str:
    sign = str(getattr(clef, "sign", "") or "").upper()
    if sign == "G":
        return "CLEF_G"
    if sign == "F":
        return "CLEF_F"
    if sign == "C":
        return "CLEF_C"
    return "CLEF_UNKNOWN"


def bucket_count(prefix: str, value: int) -> str:
    if value <= 0:
        bucket = "0"
    elif value <= 4:
        bucket = "1_4"
    elif value <= 16:
        bucket = "5_16"
    elif value <= 64:
        bucket = "17_64"
    else:
        bucket = "65_PLUS"
    return f"{prefix}_{bucket}"


def tokenize_musicxml(path: Path, max_events: int = DEFAULT_MAX_TOKENS - 8) -> TokenizationResult:
    """Tokenize MusicXML/MXL into stable metadata and simplified note tokens."""
    try:
        from music21 import converter, note, chord, meter, key, clef
    except Exception as error:
        return TokenizationResult([], f"music21_import_error: {error}")

    try:
        score = converter.parse(str(path))
    except Exception as error:
        return TokenizationResult([], f"parse_error: {error}")

    tokens: list[str] = []
    key_signatures = list(score.recurse().getElementsByClass(key.KeySignature))
    tokens.append(key_token(key_signatures[0].sharps if key_signatures else None))

    time_signatures = list(score.recurse().getElementsByClass(meter.TimeSignature))
    tokens.append(time_token(time_signatures[0].ratioString if time_signatures else None))

    clefs = list(score.recurse().getElementsByClass(clef.Clef))
    if clefs:
        for item in clefs[:4]:
            tokens.append(clef_token(item))
    else:
        tokens.append("CLEF_UNKNOWN")

    parts = list(score.parts)
    measures = list(score.recurse().getElementsByClass("Measure"))
    tokens.append(bucket_count("PARTS", len(parts)))
    tokens.append(bucket_count("MEASURES", len(measures)))

    events_added = 0
    for element in score.recurse().notesAndRests:
        if events_added >= max_events:
            tokens.append("TRUNCATED")
            return TokenizationResult(tokens, "truncated")
        if isinstance(element, note.Rest):
            tokens.append(f"REST_{normalize_duration(element.quarterLength)}")
        elif isinstance(element, chord.Chord):
            pitches = "_".join(sorted(p.pitchClassString for p in element.pitches[:4]))
            tokens.append(f"CHORD_{pitches}_{normalize_duration(element.quarterLength)}")
        elif isinstance(element, note.Note):
            tokens.append(f"NOTE_{element.pitch.nameWithOctave}_{normalize_duration(element.quarterLength)}")
        else:
            tokens.append("EVENT_UNKNOWN")
        events_added += 1
    return TokenizationResult(tokens, "")


def build_vocab(token_sequences: Iterable[list[str]]) -> Vocab:
    tokens: list[str] = []
    for sequence in token_sequences:
        tokens.extend(sequence)
    return Vocab(sorted(set(tokens)))

