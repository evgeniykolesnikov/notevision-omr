"""Experimental Audiveris command-line integration."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, Union

import pandas as pd

PathLike = Union[str, Path]

REPORT_COLUMNS = [
    "doc_id",
    "page_index",
    "input_path",
    "output_dir",
    "status",
    "message",
]

REQUIRED_LABEL_COLUMNS = {
    "doc_id",
    "page_index",
    "has_music",
}

REQUIRED_CANDIDATE_COLUMNS = {
    "doc_id",
    "page_index",
    "preprocessed_path",
    "exists",
}


def build_audiveris_command(
    input_path: PathLike,
    out_dir: PathLike,
    audiveris_bin: PathLike = "audiveris",
) -> list[str]:
    """Build an Audiveris batch command that exports MusicXML."""
    return [
        str(audiveris_bin),
        "-batch",
        "-transcribe",
        "-export",
        "-output",
        str(Path(out_dir)),
        "--",
        str(Path(input_path)),
    ]


def run_audiveris(
    input_path: PathLike,
    out_dir: PathLike,
    audiveris_bin: PathLike = "audiveris",
) -> dict[str, object]:
    """Run Audiveris and return a structured status instead of raising."""
    source = Path(input_path)
    destination = Path(out_dir)
    destination.mkdir(parents=True, exist_ok=True)
    log_path = destination / f"{source.stem}_audiveris.log"

    if not source.is_file():
        message = f"Input image does not exist: {source}"
        log_path.write_text(f"{message}\n", encoding="utf-8")
        return {
            "status": "failed",
            "message": message,
            "returncode": None,
            "log_path": str(log_path),
            "command": build_audiveris_command(
                source,
                destination,
                audiveris_bin,
            ),
        }

    command = build_audiveris_command(source, destination, audiveris_bin)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError:
        message = (
            f"Audiveris executable was not found: {audiveris_bin}. "
            "Install Audiveris or pass --audiveris-bin."
        )
        log_path.write_text(f"{message}\n", encoding="utf-8")
        return {
            "status": "failed",
            "message": message,
            "returncode": None,
            "log_path": str(log_path),
            "command": command,
        }
    except OSError as error:
        message = f"Could not start Audiveris: {error}"
        log_path.write_text(f"{message}\n", encoding="utf-8")
        return {
            "status": "failed",
            "message": message,
            "returncode": None,
            "log_path": str(log_path),
            "command": command,
        }

    log_path.write_text(
        "\n".join(
            [
                f"Command: {subprocess.list2cmdline(command)}",
                f"Return code: {completed.returncode}",
                "",
                "STDOUT",
                completed.stdout or "",
                "",
                "STDERR",
                completed.stderr or "",
                "",
            ]
        ),
        encoding="utf-8",
    )

    if completed.returncode == 0:
        status = "success"
        message = ""
    else:
        status = "failed"
        message = (
            f"Audiveris exited with code {completed.returncode}. "
            f"See log: {log_path}"
        )

    return {
        "status": status,
        "message": message,
        "returncode": completed.returncode,
        "log_path": str(log_path),
        "command": command,
    }


def run_audiveris_batch(
    labels_df: pd.DataFrame,
    preprocessed_dir: PathLike,
    out_dir: PathLike,
    *,
    limit: int | None = None,
    audiveris_bin: PathLike = "audiveris",
    runner: Callable[..., dict[str, object]] = run_audiveris,
) -> pd.DataFrame:
    """Run Audiveris for labeled music pages and return a report."""
    missing = REQUIRED_LABEL_COLUMNS.difference(labels_df.columns)
    if missing:
        missing_names = ", ".join(sorted(missing))
        raise ValueError(f"Labels are missing required columns: {missing_names}")
    if limit is not None and limit <= 0:
        raise ValueError(f"limit must be a positive integer, got: {limit}")

    selected = labels_df[labels_df["has_music"] == 1].sort_values(
        ["doc_id", "page_index"],
        kind="stable",
    )
    if limit is not None:
        selected = selected.head(limit)

    preprocessed_root = Path(preprocessed_dir)
    output_root = Path(out_dir)
    rows: list[dict[str, object]] = []

    for page in selected.itertuples(index=False):
        page_index = int(page.page_index)
        input_path = (
            preprocessed_root
            / str(page.doc_id)
            / f"page_{page_index:03d}_binary.png"
        )
        page_output_dir = output_root / str(page.doc_id)
        result = runner(
            input_path,
            page_output_dir,
            audiveris_bin=audiveris_bin,
        )
        rows.append(
            {
                "doc_id": page.doc_id,
                "page_index": page_index,
                "input_path": str(input_path),
                "output_dir": str(page_output_dir),
                "status": result["status"],
                "message": result["message"],
            }
        )

    return pd.DataFrame(rows, columns=REPORT_COLUMNS)


def _existing_candidate_mask(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin(
        {"true", "1", "yes"}
    )


def run_audiveris_candidates(
    candidates_df: pd.DataFrame,
    out_dir: PathLike,
    *,
    limit: int | None = None,
    audiveris_bin: PathLike = "audiveris",
    runner: Callable[..., dict[str, object]] = run_audiveris,
) -> pd.DataFrame:
    """Run Audiveris for existing pages listed in an OMR candidates CSV."""
    missing = REQUIRED_CANDIDATE_COLUMNS.difference(candidates_df.columns)
    if missing:
        missing_names = ", ".join(sorted(missing))
        raise ValueError(
            f"Candidates are missing required columns: {missing_names}"
        )
    if limit is not None and limit <= 0:
        raise ValueError(f"limit must be a positive integer, got: {limit}")

    selected = candidates_df[
        _existing_candidate_mask(candidates_df["exists"])
    ].sort_values(
        ["doc_id", "page_index"],
        kind="stable",
    )
    if limit is not None:
        selected = selected.head(limit)

    output_root = Path(out_dir)
    rows: list[dict[str, object]] = []
    for page in selected.itertuples(index=False):
        page_index = int(page.page_index)
        input_path = Path(str(page.preprocessed_path))
        page_output_dir = (
            output_root
            / str(page.doc_id)
            / f"page_{page_index:03d}"
        )
        result = runner(
            input_path,
            page_output_dir,
            audiveris_bin=audiveris_bin,
        )
        rows.append(
            {
                "doc_id": page.doc_id,
                "page_index": page_index,
                "input_path": str(input_path),
                "output_dir": str(page_output_dir),
                "status": result["status"],
                "message": result["message"],
            }
        )

    return pd.DataFrame(rows, columns=REPORT_COLUMNS)
