"""Try preprocessing variants for pages still failing after the 400 DPI fallback."""

from __future__ import annotations

import argparse
import csv
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from scripts.run_omr_fallback_dpi import (
    default_audiveris_runner,
    default_midi_converter,
    find_existing_mxl,
)

VARIANTS = (
    "crop_page",
    "crop_deskew",
    "crop_deskew_clahe",
    "crop_deskew_adaptive_threshold",
)
REPORT_COLUMNS = (
    "doc_id",
    "page_index",
    "variant",
    "input_path",
    "preprocessed_path",
    "preprocessing_fallback_status",
    "preprocessing_mxl_path",
    "preprocessing_midi_path",
    "preprocessing_runtime_seconds",
    "preprocessing_error",
    "run_action",
)
DEFAULT_REPORT = (
    PROJECT_ROOT / "outputs" / "reports" / "omr_preprocessing_fallback_report.csv"
)
DEFAULT_SUMMARY = (
    PROJECT_ROOT / "outputs" / "reports" / "omr_preprocessing_fallback_summary.md"
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Fallback report does not exist: {path}")
    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        required = {"doc_id", "page_index", "fallback_400_status"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                "400 DPI fallback report is missing required columns: "
                + ", ".join(sorted(missing))
            )
        return list(reader)


def select_preprocessing_failures(
    report_path: Path,
    *,
    doc_id: str | None = None,
    page_index: int | None = None,
    limit: int | None = None,
) -> list[dict[str, object]]:
    """Select pages that still have no MXL after the 400 DPI experiment."""
    selected: dict[tuple[str, int], dict[str, object]] = {}
    for row in _read_csv(report_path):
        if str(row["fallback_400_status"]).strip() != "still_failed":
            continue
        row_doc_id = str(row["doc_id"]).strip()
        try:
            row_page_index = int(float(str(row["page_index"]).strip()))
        except ValueError as error:
            raise ValueError(f"Invalid page_index for {row_doc_id}") from error
        if doc_id and row_doc_id != doc_id:
            continue
        if page_index is not None and row_page_index != page_index:
            continue
        selected[(row_doc_id, row_page_index)] = {
            "doc_id": row_doc_id,
            "page_index": row_page_index,
        }
    pages = [selected[key] for key in sorted(selected)]
    if limit is not None:
        if limit <= 0:
            raise ValueError("limit must be a positive integer")
        pages = pages[:limit]
    return pages


def find_source_image(
    pages_dir: Path,
    doc_id: str,
    page_index: int,
    *,
    fallback_400_dir: Path | None = None,
) -> Path:
    """Prefer the existing 400 DPI extraction and fall back to pipeline pages."""
    fallback_root = fallback_400_dir or (
        PROJECT_ROOT / "outputs" / "omr_400dpi_fallback"
    )
    high_resolution = (
        fallback_root
        / doc_id
        / f"page_{page_index:03d}"
        / f"page_{page_index:03d}_400dpi.png"
    )
    if high_resolution.is_file():
        return high_resolution
    regular = pages_dir / doc_id / f"page_{page_index:03d}.png"
    if regular.is_file():
        return regular
    raise FileNotFoundError(
        f"No source image found for {doc_id}/page_{page_index:03d}"
    )


def _crop_page(grayscale):
    import cv2
    import numpy as np

    blurred = cv2.GaussianBlur(grayscale, (5, 5), 0)
    _, ink = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    coordinates = cv2.findNonZero(ink)
    if coordinates is None:
        return grayscale.copy()
    x, y, width, height = cv2.boundingRect(coordinates)
    pad_x = max(10, int(grayscale.shape[1] * 0.015))
    pad_y = max(10, int(grayscale.shape[0] * 0.015))
    x0 = max(0, x - pad_x)
    y0 = max(0, y - pad_y)
    x1 = min(grayscale.shape[1], x + width + pad_x)
    y1 = min(grayscale.shape[0], y + height + pad_y)
    cropped = grayscale[y0:y1, x0:x1]
    return cropped if cropped.size else np.array(grayscale, copy=True)


def _deskew(grayscale):
    import cv2
    import numpy as np

    _, ink = cv2.threshold(
        grayscale, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    points = np.column_stack(np.where(ink > 0))
    if len(points) < 20:
        return grayscale.copy()
    angle = cv2.minAreaRect(points[:, ::-1].astype("float32"))[-1]
    angle = -(90 + angle) if angle < -45 else -angle
    if abs(angle) < 0.05 or abs(angle) > 15:
        return grayscale.copy()
    height, width = grayscale.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    return cv2.warpAffine(
        grayscale,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255,
    )


def prepare_preprocessing_variants(
    source_path: Path,
    destination_dir: Path,
) -> dict[str, Path]:
    """Create four deterministic crop/deskew/contrast variants."""
    import cv2

    grayscale = cv2.imread(str(source_path), cv2.IMREAD_GRAYSCALE)
    if grayscale is None:
        raise ValueError(f"Could not read page image: {source_path}")
    cropped = _crop_page(grayscale)
    deskewed = _deskew(cropped)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(deskewed)
    adaptive = cv2.adaptiveThreshold(
        clahe,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        41,
        15,
    )
    images = {
        "crop_page": cropped,
        "crop_deskew": deskewed,
        "crop_deskew_clahe": clahe,
        "crop_deskew_adaptive_threshold": adaptive,
    }
    destination_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for variant, image in images.items():
        path = destination_dir / f"{variant}.png"
        if not cv2.imwrite(str(path), image):
            raise OSError(f"Could not write preprocessed image: {path}")
        paths[variant] = path
    return paths


def _find_midi(midi_dir: Path, doc_id: str, page_index: int, variant: str) -> Path | None:
    candidate = midi_dir / doc_id / f"page_{page_index:03d}" / f"{variant}.mid"
    return candidate if candidate.is_file() else None


def _relative(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def run_preprocessing_fallback(
    pages: list[dict[str, object]],
    *,
    pages_dir: Path,
    out_dir: Path,
    midi_dir: Path,
    fallback_400_dir: Path | None = None,
    skip_existing: bool = False,
    resume: bool = False,
    audiveris_bin: str = "audiveris",
    variant_preparer: Callable[[Path, Path], dict[str, Path]] = (
        prepare_preprocessing_variants
    ),
    audiveris_runner: Callable[..., dict[str, object]] = default_audiveris_runner,
    midi_converter: Callable[[Path, Path], dict[str, str]] = default_midi_converter,
    clock: Callable[[], float] = time.perf_counter,
) -> list[dict[str, object]]:
    """Run every preprocessing variant for every unresolved page."""
    rows: list[dict[str, object]] = []
    for page in pages:
        doc_id = str(page["doc_id"])
        page_index = int(page["page_index"])
        try:
            source = find_source_image(
                pages_dir,
                doc_id,
                page_index,
                fallback_400_dir=fallback_400_dir,
            )
            variant_paths = variant_preparer(
                source,
                out_dir / doc_id / f"page_{page_index:03d}" / "images",
            )
        except Exception as error:
            for variant in VARIANTS:
                rows.append(
                    {
                        "doc_id": doc_id,
                        "page_index": page_index,
                        "variant": variant,
                        "input_path": "",
                        "preprocessed_path": "",
                        "preprocessing_fallback_status": "preprocessing_failed",
                        "preprocessing_mxl_path": "",
                        "preprocessing_midi_path": "",
                        "preprocessing_runtime_seconds": 0.0,
                        "preprocessing_error": str(error),
                        "run_action": "not_run",
                    }
                )
            continue

        for variant in VARIANTS:
            started = clock()
            input_path = variant_paths[variant]
            variant_dir = (
                out_dir / doc_id / f"page_{page_index:03d}" / variant
            )
            midi_path = (
                midi_dir / doc_id / f"page_{page_index:03d}" / f"{variant}.mid"
            )
            found_mxl = find_existing_mxl(
                variant_dir,
                input_path=input_path,
                page_index=page_index,
            )
            found_midi = _find_midi(midi_dir, doc_id, page_index, variant)
            existing_mxl = found_mxl if (skip_existing or resume) else None
            existing_midi = found_midi if (skip_existing or resume) else None
            action = "resumed" if resume else "processed"
            error = ""

            if existing_mxl is not None and existing_midi is not None:
                mxl_path = existing_mxl
                midi_result_path = existing_midi
                status = "recovered_midi"
                action = "skipped"
            else:
                mxl_path = existing_mxl
                midi_result_path = existing_midi
                try:
                    if mxl_path is None:
                        result = audiveris_runner(
                            input_path,
                            variant_dir,
                            audiveris_bin=audiveris_bin,
                        )
                        if result.get("status") != "success":
                            raise RuntimeError(
                                str(result.get("message") or "Audiveris failed")
                            )
                        mxl_path = find_existing_mxl(
                            variant_dir,
                            input_path=input_path,
                            page_index=page_index,
                        )
                        if mxl_path is None:
                            raise RuntimeError(
                                "Audiveris finished without an MXL export"
                            )
                    if midi_result_path is None:
                        conversion = midi_converter(mxl_path, midi_path)
                        if conversion.get("status") != "success":
                            raise RuntimeError(
                                str(
                                    conversion.get("message")
                                    or "MIDI conversion failed"
                                )
                            )
                        midi_result_path = (
                            midi_path
                            if midi_path.is_file()
                            else Path(conversion.get("midi_path", midi_path))
                        )
                    status = "recovered_midi"
                except Exception as exception:
                    error = str(exception)
                    status = "recovered_mxl" if mxl_path is not None else "still_failed"

            rows.append(
                {
                    "doc_id": doc_id,
                    "page_index": page_index,
                    "variant": variant,
                    "input_path": _relative(source),
                    "preprocessed_path": _relative(input_path),
                    "preprocessing_fallback_status": status,
                    "preprocessing_mxl_path": _relative(mxl_path),
                    "preprocessing_midi_path": _relative(midi_result_path),
                    "preprocessing_runtime_seconds": round(
                        max(0.0, clock() - started), 6
                    ),
                    "preprocessing_error": error,
                    "run_action": action,
                }
            )
    return rows


def summarize_preprocessing_fallback(
    rows: list[dict[str, object]],
) -> dict[str, object]:
    """Aggregate per-variant results into page-level recovery statistics."""
    grouped: defaultdict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["doc_id"]), int(row["page_index"]))].append(row)
    recovered_pages = []
    still_failed = []
    best_variants = {}
    for key, page_rows in grouped.items():
        recovered = [
            row
            for row in page_rows
            if row["preprocessing_fallback_status"]
            in {"recovered_mxl", "recovered_midi"}
        ]
        if recovered:
            recovered.sort(
                key=lambda row: (
                    row["preprocessing_fallback_status"] != "recovered_midi",
                    VARIANTS.index(str(row["variant"])),
                )
            )
            best = recovered[0]
            recovered_pages.append(key)
            best_variants[key] = str(best["variant"])
        else:
            still_failed.append(key)
    variant_counts = Counter(str(row["variant"]) for row in rows)
    variant_runtime = {
        variant: sum(
            float(row["preprocessing_runtime_seconds"])
            for row in rows
            if row["variant"] == variant
        )
        for variant in VARIANTS
    }
    variant_recovered_mxl = {
        variant: sum(
            row["preprocessing_fallback_status"]
            in {"recovered_mxl", "recovered_midi"}
            for row in rows
            if row["variant"] == variant
        )
        for variant in VARIANTS
    }
    variant_recovered_midi = {
        variant: sum(
            row["preprocessing_fallback_status"] == "recovered_midi"
            for row in rows
            if row["variant"] == variant
        )
        for variant in VARIANTS
    }
    return {
        "pages_attempted": len(grouped),
        "variants_run": dict(variant_counts),
        "recovered_pages": len(recovered_pages),
        "still_failed_pages": len(still_failed),
        "recovery_rate": len(recovered_pages) / len(grouped) if grouped else 0.0,
        "best_variants": best_variants,
        "still_failed": still_failed,
        "variant_runtime_seconds": variant_runtime,
        "variant_recovered_mxl": variant_recovered_mxl,
        "variant_recovered_midi": variant_recovered_midi,
    }


def build_summary_markdown(summary: dict[str, object]) -> str:
    runtime_rows = "\n".join(
        f"| `{variant}` | {summary['variants_run'].get(variant, 0)} | "
        f"{summary['variant_recovered_mxl'].get(variant, 0)} | "
        f"{summary['variant_recovered_midi'].get(variant, 0)} | "
        f"{summary['variant_runtime_seconds'].get(variant, 0.0):.2f} |"
        for variant in VARIANTS
    )
    best_rows = "\n".join(
        f"| `{doc_id}` | {page_index} | `{variant}` |"
        for (doc_id, page_index), variant in sorted(
            summary["best_variants"].items()
        )
    ) or "| Нет восстановленных страниц |  |  |"
    failed_rows = "\n".join(
        f"- `{doc_id}/page_{page_index:03d}`"
        for doc_id, page_index in summary["still_failed"]
    ) or "- Нет"
    return f"""# OMR preprocessing fallback experiment

Эксперимент выполняется только для страниц, которые не дали MXL в основном OMR
при 300 DPI и в fallback-прогоне 400 DPI. Он не заменяет основную техническую
метрику OMR и учитывается как отдельный исследовательский этап.

| Показатель | Значение |
|---|---:|
| Страниц проверено | {summary['pages_attempted']} |
| Страниц recovered после preprocessing | {summary['recovered_pages']} |
| Страниц всё ещё failed | {summary['still_failed_pages']} |
| Recovery rate | {float(summary['recovery_rate']):.2%} |

## Runtime по вариантам

| Вариант | Запусков | MXL | MIDI | Runtime, секунд |
|---|---:|---:|---:|---:|
{runtime_rows}

## Лучший recovered variant

| doc_id | page_index | Вариант |
|---|---:|---|
{best_rows}

## Всё ещё failed

{failed_rows}
"""


def write_reports(
    rows: list[dict[str, object]],
    report_path: Path,
    summary_path: Path,
) -> dict[str, object]:
    summary = summarize_preprocessing_fallback(rows)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=REPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(build_summary_markdown(summary), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--failures-report",
        type=Path,
        default=PROJECT_ROOT
        / "outputs"
        / "reports"
        / "omr_400dpi_fallback_report.csv",
    )
    parser.add_argument(
        "--pages-dir", type=Path, default=PROJECT_ROOT / "outputs" / "pages"
    )
    parser.add_argument(
        "--fallback-400-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "omr_400dpi_fallback",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "omr_preprocessed_fallback",
    )
    parser.add_argument(
        "--midi-dir",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "midi_preprocessed_fallback",
    )
    parser.add_argument("--audiveris-bin", default="audiveris")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--doc-id")
    parser.add_argument("--page-index", type=int)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        pages = select_preprocessing_failures(
            args.failures_report,
            doc_id=args.doc_id,
            page_index=args.page_index,
            limit=args.limit,
        )
        rows = run_preprocessing_fallback(
            pages,
            pages_dir=args.pages_dir,
            fallback_400_dir=args.fallback_400_dir,
            out_dir=args.out_dir,
            midi_dir=args.midi_dir,
            skip_existing=args.skip_existing or args.resume,
            resume=args.resume,
            audiveris_bin=args.audiveris_bin,
        )
        summary = write_reports(rows, args.report_out, args.summary_out)
    except (FileNotFoundError, ValueError, OSError, csv.Error) as error:
        raise SystemExit(f"Error: {error}") from error

    print(f"Pages attempted: {summary['pages_attempted']}")
    print(f"Recovered pages: {summary['recovered_pages']}")
    print(f"Still failed: {summary['still_failed_pages']}")
    print(f"Report: {args.report_out}")
    print(f"Summary: {args.summary_out}")


if __name__ == "__main__":
    main()
