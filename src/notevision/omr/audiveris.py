"""Experimental Audiveris command-line integration."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, Union

import pandas as pd

from notevision.omr.candidate_adapter import (
    NORMALIZED_EXISTS,
    NORMALIZED_INPUT_KIND,
    NORMALIZED_INPUT_PATH,
    NORMALIZED_SELECTED,
    adapt_omr_candidates,
)

PathLike = Union[str, Path]

REPORT_COLUMNS = [
    "doc_id",
    "page_index",
    "input_path",
    "input_kind",
    "output_dir",
    "status",
    "message",
    "run_action",
]

REQUIRED_LABEL_COLUMNS = {
    "doc_id",
    "page_index",
    "has_music",
}


def find_existing_mxl(
    output_dir: PathLike,
    *,
    input_path: PathLike | None = None,
    page_index: int | None = None,
) -> Path | None:
    """Find an existing MXL export for one page."""
    destination = Path(output_dir)
    if not destination.is_dir():
        return None

    patterns: list[str] = []
    if page_index is not None:
        patterns.append(f"page_{page_index:03d}*.mxl")
    if input_path is not None:
        input_stem = Path(input_path).stem
        patterns.append(f"{input_stem}*.mxl")
        if input_stem.endswith("_binary"):
            patterns.append(f"{input_stem.removesuffix('_binary')}*.mxl")

    candidates: set[Path] = set()
    for pattern in patterns:
        candidates.update(destination.glob(pattern))

    if destination.name.startswith("page_"):
        candidates.update(destination.glob("*.mxl"))

    files = sorted(
        (path for path in candidates if path.is_file()),
        key=lambda path: str(path).lower(),
    )
    return files[0] if files else None


def _existing_mxl_result(existing_mxl: Path) -> dict[str, object]:
    return {
        "status": "success",
        "message": f"Existing MXL found: {existing_mxl}",
        "run_action": "skipped",
    }


def _run_page(
    input_path: Path,
    output_dir: Path,
    *,
    page_index: int,
    skip_existing: bool,
    resume: bool,
    audiveris_bin: PathLike,
    runner: Callable[..., dict[str, object]],
) -> dict[str, object]:
    """Skip an existing export or invoke Audiveris for one page."""
    if skip_existing or resume:
        existing_mxl = find_existing_mxl(
            output_dir,
            input_path=input_path,
            page_index=page_index,
        )
        if existing_mxl is not None:
            return _existing_mxl_result(existing_mxl)

    result = runner(
        input_path,
        output_dir,
        audiveris_bin=audiveris_bin,
    )
    return {
        **result,
        "run_action": "resumed" if resume else "processed",
    }


def summarize_run_actions(report: pd.DataFrame) -> dict[str, int]:
    """Count skipped, resumed, and invoked pages in an OMR report."""
    if "run_action" not in report.columns:
        raise ValueError("OMR report is missing required column: run_action")
    actions = report["run_action"].astype(str)
    resumed = int((actions == "resumed").sum())
    skipped = int((actions == "skipped").sum())
    processed = int(actions.isin(["processed", "resumed"]).sum())
    return {
        "skipped": skipped,
        "resumed": resumed,
        "processed": processed,
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
    skip_existing: bool = False,
    resume: bool = False,
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
        result = _run_page(
            input_path,
            page_output_dir,
            page_index=page_index,
            skip_existing=skip_existing,
            resume=resume,
            audiveris_bin=audiveris_bin,
            runner=runner,
        )
        rows.append(
            {
                "doc_id": page.doc_id,
                "page_index": page_index,
                "input_path": str(input_path),
                "input_kind": "preprocessed",
                "output_dir": str(page_output_dir),
                "status": result["status"],
                "message": result["message"],
                "run_action": result["run_action"],
            }
        )

    return pd.DataFrame(rows, columns=REPORT_COLUMNS)


def run_audiveris_candidates(
    candidates_df: pd.DataFrame,
    out_dir: PathLike,
    *,
    omr_pages_dir: PathLike | None = None,
    limit: int | None = None,
    skip_existing: bool = False,
    resume: bool = False,
    audiveris_bin: PathLike = "audiveris",
    runner: Callable[..., dict[str, object]] = run_audiveris,
) -> pd.DataFrame:
    """Run Audiveris for existing pages listed in an OMR candidates CSV."""
    normalized = adapt_omr_candidates(candidates_df)
    if limit is not None and limit <= 0:
        raise ValueError(f"limit must be a positive integer, got: {limit}")

    if omr_pages_dir is None:
        selected = normalized[
            normalized[NORMALIZED_SELECTED]
            & normalized[NORMALIZED_EXISTS]
        ]
    else:
        selected = normalized[normalized[NORMALIZED_SELECTED]]

    selected = selected.sort_values(
        ["doc_id", "page_index"],
        kind="stable",
    )
    if limit is not None:
        selected = selected.head(limit)

    output_root = Path(out_dir)
    rows: list[dict[str, object]] = []
    for page in selected.to_dict(orient="records"):
        page_index = int(page["page_index"])
        doc_id = str(page["doc_id"])
        if omr_pages_dir is None:
            input_path = Path(str(page[NORMALIZED_INPUT_PATH]))
            input_kind = str(page[NORMALIZED_INPUT_KIND])
        else:
            input_path = (
                Path(omr_pages_dir)
                / doc_id
                / f"page_{page_index:03d}.png"
            )
            input_kind = "omr_pages_300dpi"
        page_output_dir = (
            output_root
            / doc_id
            / f"page_{page_index:03d}"
        )
        if omr_pages_dir is not None and not input_path.is_file():
            result = {
                "status": "failed",
                "message": f"High-resolution OMR page does not exist: {input_path}",
                "run_action": "not_run",
            }
        else:
            result = _run_page(
                input_path,
                page_output_dir,
                page_index=page_index,
                skip_existing=skip_existing,
                resume=resume,
                audiveris_bin=audiveris_bin,
                runner=runner,
            )
        rows.append(
            {
                "doc_id": doc_id,
                "page_index": page_index,
                "input_path": str(input_path),
                "input_kind": input_kind,
                "output_dir": str(page_output_dir),
                "status": result["status"],
                "message": result["message"],
                "run_action": result["run_action"],
            }
        )

    return pd.DataFrame(rows, columns=REPORT_COLUMNS)
