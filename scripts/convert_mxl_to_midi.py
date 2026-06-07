"""Convert MXL/MusicXML files to MIDI with repeat-related fallbacks."""

import argparse
import re
from pathlib import Path
from typing import Any, Callable

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = PROJECT_ROOT / "outputs" / "reports" / "midi_conversion_report.csv"

REPORT_COLUMNS = [
    "source_mxl",
    "midi_path",
    "status",
    "message",
    "mode",
]


def build_batch_midi_path(
    source_mxl: Path,
    input_dir: Path,
    output_dir: Path,
) -> Path:
    """Build ``<output>/<doc_id>/page_XXX.mid`` for an MXL file."""
    relative = source_mxl.relative_to(input_dir)
    if len(relative.parts) < 2:
        raise ValueError(
            f"Could not determine doc_id from MXL path: {source_mxl}"
        )

    doc_id = relative.parts[0]
    page_match = re.search(r"page_(\d+)", source_mxl.stem)
    if page_match is None:
        page_match = re.search(r"page_(\d+)", source_mxl.parent.name)
    if page_match is None:
        raise ValueError(
            f"Could not determine page index from MXL path: {source_mxl}"
        )

    page_index = int(page_match.group(1))
    return output_dir / doc_id / f"page_{page_index:03d}.mid"


def find_mxl_files(input_dir: Path, limit: int | None = None) -> list[Path]:
    """Find MXL files recursively in deterministic order."""
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")
    if limit is not None and limit <= 0:
        raise ValueError(f"limit must be a positive integer, got: {limit}")

    files = sorted(input_dir.rglob("*.mxl"), key=lambda path: str(path).lower())
    return files[:limit] if limit is not None else files


def _remove_repeats(score: Any, bar_module: Any, repeat_module: Any) -> None:
    for measure in score.recurse().getElementsByClass("Measure"):
        if isinstance(measure.leftBarline, bar_module.Repeat):
            measure.leftBarline = None
        if isinstance(measure.rightBarline, bar_module.Repeat):
            measure.rightBarline = None

    repeat_expressions = list(
        score.recurse().getElementsByClass(repeat_module.RepeatExpression)
    )
    for expression in repeat_expressions:
        if expression.activeSite is not None:
            expression.activeSite.remove(expression)


def _write_flat_fallback(score: Any, midi_path: Path) -> None:
    flat_stream = score.flatten().notesAndRests.stream()
    flat_stream.write("midi", fp=str(midi_path))


def convert_mxl_to_midi(
    source_mxl: Path,
    midi_path: Path,
    *,
    parser: Callable[[str], Any] | None = None,
    expander_exception: type[Exception] | None = None,
    repeat_cleaner: Callable[[Any], None] | None = None,
) -> dict[str, str]:
    """Convert one MXL file using normal, no-repeat, and flat modes."""
    if not source_mxl.is_file():
        return {
            "source_mxl": str(source_mxl),
            "midi_path": str(midi_path),
            "status": "failed",
            "message": f"MXL file does not exist: {source_mxl}",
            "mode": "normal",
        }

    if parser is None or expander_exception is None or repeat_cleaner is None:
        from music21 import bar, converter, repeat

        parser = parser or converter.parse
        expander_exception = expander_exception or repeat.ExpanderException
        repeat_cleaner = repeat_cleaner or (
            lambda score: _remove_repeats(score, bar, repeat)
        )

    midi_path.parent.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    try:
        score = parser(str(source_mxl))
        score.write("midi", fp=str(midi_path))
        return {
            "source_mxl": str(source_mxl),
            "midi_path": str(midi_path),
            "status": "success",
            "message": "",
            "mode": "normal",
        }
    except expander_exception as error:
        errors.append(f"normal: {error}")
    except Exception as error:
        errors.append(f"normal: {error}")
        try:
            score = parser(str(source_mxl))
            _write_flat_fallback(score, midi_path)
            return {
                "source_mxl": str(source_mxl),
                "midi_path": str(midi_path),
                "status": "success",
                "message": " | ".join(errors),
                "mode": "flat_fallback",
            }
        except Exception as fallback_error:
            errors.append(f"flat_fallback: {fallback_error}")
            return {
                "source_mxl": str(source_mxl),
                "midi_path": str(midi_path),
                "status": "failed",
                "message": " | ".join(errors),
                "mode": "flat_fallback",
            }

    try:
        score = parser(str(source_mxl))
        repeat_cleaner(score)
        score.write("midi", fp=str(midi_path))
        return {
            "source_mxl": str(source_mxl),
            "midi_path": str(midi_path),
            "status": "success",
            "message": " | ".join(errors),
            "mode": "no_repeats",
        }
    except Exception as error:
        errors.append(f"no_repeats: {error}")

    try:
        score = parser(str(source_mxl))
        _write_flat_fallback(score, midi_path)
        return {
            "source_mxl": str(source_mxl),
            "midi_path": str(midi_path),
            "status": "success",
            "message": " | ".join(errors),
            "mode": "flat_fallback",
        }
    except Exception as error:
        errors.append(f"flat_fallback: {error}")
        return {
            "source_mxl": str(source_mxl),
            "midi_path": str(midi_path),
            "status": "failed",
            "message": " | ".join(errors),
            "mode": "flat_fallback",
        }


def convert_mxl_batch(
    input_dir: Path,
    output_dir: Path,
    *,
    limit: int | None = None,
    converter_func: Callable[[Path, Path], dict[str, str]] = convert_mxl_to_midi,
) -> pd.DataFrame:
    """Convert every MXL under ``input_dir`` without stopping on errors."""
    rows: list[dict[str, str]] = []
    for source_mxl in find_mxl_files(input_dir, limit=limit):
        try:
            midi_path = build_batch_midi_path(
                source_mxl,
                input_dir,
                output_dir,
            )
            result = converter_func(source_mxl, midi_path)
        except Exception as error:
            result = {
                "source_mxl": str(source_mxl),
                "midi_path": "",
                "status": "failed",
                "message": str(error),
                "mode": "normal",
            }
        rows.append(result)

    return pd.DataFrame(rows, columns=REPORT_COLUMNS)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--input", type=Path)
    source_group.add_argument("--input-dir", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    if args.input is not None and args.out is None:
        parser.error("--out is required with --input")
    if args.input_dir is not None and args.out_dir is None:
        parser.error("--out-dir is required with --input-dir")
    return args


def main() -> None:
    """Run one-file or batch MIDI conversion and save the report."""
    args = parse_args()
    if args.input is not None:
        report = pd.DataFrame(
            [convert_mxl_to_midi(args.input, args.out)],
            columns=REPORT_COLUMNS,
        )
    else:
        report = convert_mxl_batch(
            args.input_dir,
            args.out_dir,
            limit=args.limit,
        )

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(REPORT_PATH, index=False)
    successful = int((report["status"] == "success").sum())
    failed = int((report["status"] == "failed").sum())
    print(f"MXL files processed: {len(report)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
