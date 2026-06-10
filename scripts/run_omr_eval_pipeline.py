"""Run the complete primary and fallback OMR evaluation pipeline."""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
for import_path in (PROJECT_ROOT, SRC_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from scripts.evaluate_omr_pipeline import (  # noqa: E402
    build_omr_pipeline_rows,
    inspect_omr_sample_pages,
    read_omr_sample,
)

COMBINED_COLUMNS = [
    "doc_id",
    "page_index",
    "image_path",
    "primary_has_mxl",
    "primary_has_midi",
    "fallback_400_has_mxl",
    "fallback_400_has_midi",
    "preprocessing_has_mxl",
    "preprocessing_has_midi",
    "final_has_mxl",
    "final_has_midi",
    "recovery_source",
    "final_status",
]


def _key(row: dict[str, object]) -> tuple[str, int]:
    return str(row["doc_id"]), int(row["page_index"])


def _find_page_mxl(root: Path, doc_id: str, page_index: int) -> Path | None:
    page_dir = root / doc_id / f"page_{page_index:03d}"
    files = sorted(page_dir.rglob("*.mxl")) if page_dir.is_dir() else []
    return files[0] if files else None


def _find_page_midi(root: Path, doc_id: str, page_index: int) -> Path | None:
    candidates = [
        root / doc_id / f"page_{page_index:03d}.mid",
        root / doc_id / f"page_{page_index:03d}.midi",
    ]
    return next((path for path in candidates if path.is_file()), None)


def _artifact_exists(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    path = Path(text)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.is_file()


def _write_csv(
    rows: list[dict[str, object]],
    path: Path,
    columns: list[str] | tuple[str, ...],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=list(columns),
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def _default_primary_runner(
    sample_rows: list[dict[str, str]],
    *,
    raw_dir: Path,
    pages_dir: Path,
    omr_dir: Path,
    midi_dir: Path,
    audiveris_bin: str,
    resume: bool,
) -> list[dict[str, object]]:
    """Extract 300 DPI pages, run Audiveris, and convert missing MIDI."""
    import pandas as pd

    from notevision.omr.audiveris import run_audiveris_candidates
    from scripts.convert_mxl_to_midi import convert_mxl_to_midi
    from scripts.extract_omr_pages import extract_omr_candidate_pages

    candidates = pd.DataFrame(sample_rows)
    if resume:
        missing_rows = [
            row
            for row in sample_rows
            if not (
                pages_dir
                / str(row["doc_id"])
                / f"page_{int(row['page_index']):03d}.png"
            ).is_file()
        ]
    else:
        missing_rows = sample_rows
    if missing_rows:
        extract_omr_candidate_pages(
            pd.DataFrame(missing_rows),
            raw_dir,
            pages_dir,
            dpi=300,
        )

    report = run_audiveris_candidates(
        candidates,
        omr_dir,
        omr_pages_dir=pages_dir,
        skip_existing=True,
        resume=resume,
        audiveris_bin=audiveris_bin,
    )

    for row in sample_rows:
        doc_id, page_index = _key(row)
        midi_path = midi_dir / doc_id / f"page_{page_index:03d}.mid"
        if midi_path.is_file():
            continue
        mxl_path = _find_page_mxl(omr_dir, doc_id, page_index)
        if mxl_path is not None:
            convert_mxl_to_midi(mxl_path, midi_path)
    return report.to_dict(orient="records")


def _default_fallback_runner(
    pages: list[dict[str, object]],
    *,
    raw_dir: Path,
    pages_dir: Path,
    out_dir: Path,
    midi_dir: Path,
    audiveris_bin: str,
    resume: bool,
) -> list[dict[str, object]]:
    from scripts.run_omr_fallback_dpi import run_fallback_pages

    return run_fallback_pages(
        pages,
        raw_dir=raw_dir,
        pages_dir=pages_dir,
        out_dir=out_dir,
        midi_dir=midi_dir,
        dpi=400,
        skip_existing=True,
        resume=resume,
        audiveris_bin=audiveris_bin,
    )


def _default_preprocessing_runner(
    pages: list[dict[str, object]],
    *,
    pages_dir: Path,
    fallback_400_dir: Path,
    out_dir: Path,
    midi_dir: Path,
    audiveris_bin: str,
    resume: bool,
) -> list[dict[str, object]]:
    from scripts.run_omr_preprocessing_fallback import (
        run_preprocessing_fallback,
    )

    return run_preprocessing_fallback(
        pages,
        pages_dir=pages_dir,
        fallback_400_dir=fallback_400_dir,
        out_dir=out_dir,
        midi_dir=midi_dir,
        skip_existing=True,
        resume=resume,
        audiveris_bin=audiveris_bin,
    )


def build_combined_rows(
    sample_rows: list[dict[str, str]],
    *,
    primary_omr_dir: Path,
    primary_midi_dir: Path,
    fallback_rows: list[dict[str, object]],
    preprocessing_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Merge primary and fallback artifact availability at page level."""
    fallback_by_key = {_key(row): row for row in fallback_rows}
    preprocessing_by_key: defaultdict[
        tuple[str, int], list[dict[str, object]]
    ] = defaultdict(list)
    for row in preprocessing_rows:
        preprocessing_by_key[_key(row)].append(row)

    combined = []
    for sample in sample_rows:
        doc_id, page_index = _key(sample)
        primary_mxl = _find_page_mxl(primary_omr_dir, doc_id, page_index)
        primary_midi = _find_page_midi(primary_midi_dir, doc_id, page_index)
        fallback = fallback_by_key.get((doc_id, page_index), {})
        fallback_mxl = _artifact_exists(
            fallback.get("fallback_400_mxl_path", "")
        )
        fallback_midi = _artifact_exists(
            fallback.get("fallback_400_midi_path", "")
        )
        preprocessing = preprocessing_by_key.get((doc_id, page_index), [])
        preprocessing_mxl = any(
            _artifact_exists(row.get("preprocessing_mxl_path", ""))
            for row in preprocessing
        )
        preprocessing_midi = any(
            _artifact_exists(row.get("preprocessing_midi_path", ""))
            for row in preprocessing
        )
        final_mxl = bool(primary_mxl) or fallback_mxl or preprocessing_mxl
        final_midi = (
            bool(primary_midi) or fallback_midi or preprocessing_midi
        )
        if primary_mxl:
            source = "primary"
        elif fallback_mxl:
            source = "fallback_400dpi"
        elif preprocessing_mxl:
            source = "preprocessing"
        else:
            source = "failed"
        status = (
            "success"
            if final_mxl and final_midi
            else "missing_midi"
            if final_mxl
            else "missing_mxl"
        )
        combined.append(
            {
                "doc_id": doc_id,
                "page_index": page_index,
                "image_path": sample.get("image_path", ""),
                "primary_has_mxl": bool(primary_mxl),
                "primary_has_midi": bool(primary_midi),
                "fallback_400_has_mxl": fallback_mxl,
                "fallback_400_has_midi": fallback_midi,
                "preprocessing_has_mxl": preprocessing_mxl,
                "preprocessing_has_midi": preprocessing_midi,
                "final_has_mxl": final_mxl,
                "final_has_midi": final_midi,
                "recovery_source": source,
                "final_status": status,
            }
        )
    return combined


def calculate_combined_summary(
    combined_rows: list[dict[str, object]],
    fallback_rows: list[dict[str, object]],
    preprocessing_rows: list[dict[str, object]],
) -> dict[str, int | float]:
    """Calculate primary, fallback, and final page-level metrics."""
    total = len(combined_rows)
    primary_mxl = sum(bool(row["primary_has_mxl"]) for row in combined_rows)
    primary_midi = sum(bool(row["primary_has_midi"]) for row in combined_rows)
    fallback_attempted = len({_key(row) for row in fallback_rows})
    fallback_mxl = sum(
        bool(row["fallback_400_has_mxl"]) for row in combined_rows
    )
    fallback_midi = sum(
        bool(row["fallback_400_has_midi"]) for row in combined_rows
    )
    preprocessing_attempted = len({_key(row) for row in preprocessing_rows})
    preprocessing_mxl = sum(
        bool(row["preprocessing_has_mxl"]) for row in combined_rows
    )
    preprocessing_midi = sum(
        bool(row["preprocessing_has_midi"]) for row in combined_rows
    )
    final_mxl = sum(bool(row["final_has_mxl"]) for row in combined_rows)
    final_midi = sum(bool(row["final_has_midi"]) for row in combined_rows)
    return {
        "sampled_pages": total,
        "primary_mxl_pages": primary_mxl,
        "primary_midi_pages": primary_midi,
        "primary_mxl_success_rate": primary_mxl / total if total else 0.0,
        "primary_midi_success_rate": primary_midi / total if total else 0.0,
        "fallback_400_attempted_pages": fallback_attempted,
        "fallback_400_recovered_mxl": fallback_mxl,
        "fallback_400_recovered_midi": fallback_midi,
        "preprocessing_attempted_pages": preprocessing_attempted,
        "preprocessing_recovered_mxl": preprocessing_mxl,
        "preprocessing_recovered_midi": preprocessing_midi,
        "final_combined_mxl_pages": final_mxl,
        "final_combined_midi_pages": final_midi,
        "final_combined_mxl_success_rate": final_mxl / total if total else 0.0,
        "final_combined_midi_success_rate": final_midi / total if total else 0.0,
        "still_failed_pages": total - final_mxl,
    }


def build_summary_markdown(
    summary: dict[str, int | float],
    *,
    sample_path: Path,
    out_root: Path,
) -> str:
    """Render the final orchestration summary."""
    return f"""# Orchestrated OMR evaluation

Sample: `{sample_path}`

Output root: `{out_root}`

| Stage | Metric | Value |
|---|---|---:|
| Primary 300 DPI | Sampled pages | {summary['sampled_pages']} |
| Primary 300 DPI | MXL pages | {summary['primary_mxl_pages']} |
| Primary 300 DPI | MIDI pages | {summary['primary_midi_pages']} |
| Primary 300 DPI | MXL success rate | {float(summary['primary_mxl_success_rate']):.2%} |
| Primary 300 DPI | MIDI success rate | {float(summary['primary_midi_success_rate']):.2%} |
| 400 DPI fallback | Attempted pages | {summary['fallback_400_attempted_pages']} |
| 400 DPI fallback | Recovered MXL | {summary['fallback_400_recovered_mxl']} |
| 400 DPI fallback | Recovered MIDI | {summary['fallback_400_recovered_midi']} |
| Preprocessing fallback | Attempted pages | {summary['preprocessing_attempted_pages']} |
| Preprocessing fallback | Recovered MXL | {summary['preprocessing_recovered_mxl']} |
| Preprocessing fallback | Recovered MIDI | {summary['preprocessing_recovered_midi']} |
| Final combined | MXL pages | {summary['final_combined_mxl_pages']} |
| Final combined | MIDI pages | {summary['final_combined_midi_pages']} |
| Final combined | MXL success rate | {float(summary['final_combined_mxl_success_rate']):.2%} |
| Final combined | MIDI success rate | {float(summary['final_combined_midi_success_rate']):.2%} |
| Final combined | Still failed pages | {summary['still_failed_pages']} |

Primary and fallback metrics are reported separately. The final combined values
describe technical MXL/MIDI artifact availability, not musical correctness.
Musical accuracy requires expert comparison with the source scan.
"""


def run_omr_eval_pipeline(
    sample_path: Path,
    *,
    pages_dir: Path,
    raw_dir: Path,
    out_root: Path,
    reports_dir: Path,
    audiveris_bin: str = "audiveris",
    resume: bool = False,
    limit: int | None = None,
    primary_runner: Callable[..., list[dict[str, object]]] = (
        _default_primary_runner
    ),
    fallback_runner: Callable[..., list[dict[str, object]]] = (
        _default_fallback_runner
    ),
    preprocessing_runner: Callable[..., list[dict[str, object]]] = (
        _default_preprocessing_runner
    ),
) -> dict[str, object]:
    """Run every OMR stage and save final page-level reports."""
    sample_rows = read_omr_sample(sample_path)
    if limit is not None:
        if limit <= 0:
            raise ValueError("limit must be a positive integer")
        sample_rows = sample_rows[:limit]

    primary_pages_dir = out_root / "primary_pages_300dpi"
    primary_omr_dir = out_root / "primary_omr"
    primary_midi_dir = out_root / "primary_midi"
    fallback_omr_dir = out_root / "fallback_400dpi_omr"
    fallback_midi_dir = out_root / "fallback_400dpi_midi"
    preprocessing_omr_dir = out_root / "preprocessing_omr"
    preprocessing_midi_dir = out_root / "preprocessing_midi"
    out_root.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    print("[1/6] Primary 300 DPI OMR and MIDI")
    primary_report = primary_runner(
        sample_rows,
        raw_dir=raw_dir,
        pages_dir=primary_pages_dir,
        omr_dir=primary_omr_dir,
        midi_dir=primary_midi_dir,
        audiveris_bin=audiveris_bin,
        resume=resume,
    )

    print("[2/6] Primary page-level evaluation")
    primary_inspected = inspect_omr_sample_pages(
        sample_rows,
        primary_omr_dir,
        primary_midi_dir,
    )
    primary_documents = build_omr_pipeline_rows(primary_inspected)
    primary_failures = [
        {
            "doc_id": row["doc_id"],
            "page_index": row["page_index"],
            "image_path": row.get("image_path", ""),
            "primary_failure_status": "missing_mxl",
        }
        for row in primary_inspected
        if not bool(row["has_mxl"])
    ]

    print("[3/6] 400 DPI fallback")
    fallback_rows = fallback_runner(
        primary_failures,
        raw_dir=raw_dir,
        pages_dir=pages_dir,
        out_dir=fallback_omr_dir,
        midi_dir=fallback_midi_dir,
        audiveris_bin=audiveris_bin,
        resume=resume,
    )
    preprocessing_pages = [
        {"doc_id": row["doc_id"], "page_index": row["page_index"]}
        for row in fallback_rows
        if str(row.get("fallback_400_status", "")) == "still_failed"
    ]

    print("[4/6] Preprocessing fallback")
    preprocessing_rows = preprocessing_runner(
        preprocessing_pages,
        pages_dir=pages_dir,
        fallback_400_dir=fallback_omr_dir,
        out_dir=preprocessing_omr_dir,
        midi_dir=preprocessing_midi_dir,
        audiveris_bin=audiveris_bin,
        resume=resume,
    )

    print("[5/6] Combined page-level report")
    combined_rows = build_combined_rows(
        sample_rows,
        primary_omr_dir=primary_omr_dir,
        primary_midi_dir=primary_midi_dir,
        fallback_rows=fallback_rows,
        preprocessing_rows=preprocessing_rows,
    )
    summary = calculate_combined_summary(
        combined_rows,
        fallback_rows,
        preprocessing_rows,
    )

    prefix = out_root.name
    paths = {
        "primary_report": reports_dir / f"{prefix}_primary_report.csv",
        "primary_failures": reports_dir / f"{prefix}_primary_failures.csv",
        "fallback_report": reports_dir / f"{prefix}_fallback_400dpi.csv",
        "preprocessing_report": reports_dir
        / f"{prefix}_preprocessing_fallback.csv",
        "combined_report": reports_dir / f"{prefix}_combined_report.csv",
        "summary": reports_dir / f"{prefix}_summary.md",
    }
    _write_csv(
        primary_documents,
        paths["primary_report"],
        [
            "doc_id",
            "sampled_pages",
            "mxl_generated_pages",
            "midi_generated_pages",
            "mxl_success_rate",
            "midi_success_rate",
        ],
    )
    _write_csv(
        primary_failures,
        paths["primary_failures"],
        ["doc_id", "page_index", "image_path", "primary_failure_status"],
    )
    if fallback_rows:
        _write_csv(
            fallback_rows,
            paths["fallback_report"],
            list(fallback_rows[0]),
        )
    else:
        _write_csv([], paths["fallback_report"], ["doc_id", "page_index"])
    if preprocessing_rows:
        _write_csv(
            preprocessing_rows,
            paths["preprocessing_report"],
            list(preprocessing_rows[0]),
        )
    else:
        _write_csv([], paths["preprocessing_report"], ["doc_id", "page_index"])
    _write_csv(combined_rows, paths["combined_report"], COMBINED_COLUMNS)
    paths["summary"].write_text(
        build_summary_markdown(
            summary,
            sample_path=sample_path,
            out_root=out_root,
        ),
        encoding="utf-8",
    )

    print("[6/6] Reports saved")
    return {
        "summary": summary,
        "paths": paths,
        "primary_runner_rows": primary_report,
        "combined_rows": combined_rows,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--pages-dir", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--reports-dir", type=Path, required=True)
    parser.add_argument("--audiveris-bin", default="audiveris")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        result = run_omr_eval_pipeline(
            args.sample,
            pages_dir=args.pages_dir,
            raw_dir=args.raw_dir,
            out_root=args.out_root,
            reports_dir=args.reports_dir,
            audiveris_bin=args.audiveris_bin,
            resume=args.resume,
            limit=args.limit,
        )
    except (FileNotFoundError, ValueError, OSError, csv.Error) as error:
        raise SystemExit(f"Error: {error}") from error

    summary = result["summary"]
    print(f"Sampled pages: {summary['sampled_pages']}")
    print(f"Primary MXL: {summary['primary_mxl_pages']}")
    print(f"Primary MIDI: {summary['primary_midi_pages']}")
    print(f"Final MXL: {summary['final_combined_mxl_pages']}")
    print(f"Final MIDI: {summary['final_combined_midi_pages']}")
    print(f"Still failed: {summary['still_failed_pages']}")
    print(f"Summary: {result['paths']['summary']}")


if __name__ == "__main__":
    main()
