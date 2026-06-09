"""Read-only data aggregation for the MVP document dashboard."""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

from review_app.database import get_item_by_page

PAGE_TYPES = ("music", "mixed", "title", "text", "blank", "unknown", "bad_scan")
FEATURE_FIELDS = (
    "key_name_ru",
    "key_name_latin",
    "time_signature",
    "clefs",
    "instruments",
    "confidence",
    "source",
)
REPORTS = (
    ("dataset_statistics", "Dataset statistics", "docs/thesis/dataset_statistics.md"),
    (
        "corpus_analysis",
        "Corpus analysis run summary",
        "outputs/reports/corpus_analysis_run_summary.md",
    ),
    (
        "expert_summary",
        "Expert review summary",
        "outputs/reports/expert_review_summary.md",
    ),
    (
        "expert_metrics",
        "Expert review metrics",
        "outputs/reports/expert_review_metrics.csv",
    ),
    (
        "fallback_400",
        "400 DPI fallback summary",
        "outputs/reports/omr_400dpi_fallback_summary.md",
    ),
    (
        "preprocessing_fallback",
        "Preprocessing fallback summary",
        "outputs/reports/omr_preprocessing_fallback_summary.md",
    ),
    (
        "music_features",
        "Music features summary",
        "outputs/reports/music_features_summary.md",
    ),
)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Return CSV rows or an empty list when an optional report is absent."""
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def _integer(value: object, default: int = 0) -> int:
    try:
        return int(float(str(value or "").strip()))
    except ValueError:
        return default


def _is_recovered(value: object) -> bool:
    text = str(value or "").strip().lower()
    return bool(text) and (
        "recover" in text
        or text in {"success", "succeeded", "mxl_generated", "midi_generated"}
    )


def _features(row: dict[str, str] | None) -> dict[str, str]:
    source = row or {}
    return {
        field: str(source.get(field, "")).strip() or "unknown"
        for field in FEATURE_FIELDS
    }


def _safe_file(base: Path, relative_path: object) -> Path | None:
    value = str(relative_path or "").strip()
    if not value:
        return None
    root = base.resolve()
    candidate = (root / value).resolve()
    return candidate if _is_within(candidate, root) and candidate.is_file() else None


def _audio_paths(
    project_root: Path,
    package_dir: Path,
    review_item: dict[str, object] | None,
    doc_id: str,
    page_index: int,
) -> tuple[Path | None, list[Path]]:
    audio: Path | None = None
    tracks: list[Path] = []
    if review_item:
        audio = _safe_file(package_dir, review_item.get("audio_path"))
        tracks = [
            path
            for value in review_item.get("track_paths", [])
            if (path := _safe_file(package_dir, value)) is not None
        ]

    page_name = f"page_{page_index:03d}"
    package_root = package_dir.resolve()
    if audio is None and package_root.is_dir():
        for extension in ("mp3", "wav", "ogg"):
            matches = sorted(
                package_root.glob(f"*_{doc_id}_{page_name}_audio.{extension}")
            )
            if matches:
                audio = matches[0].resolve()
                break
    if not tracks and package_root.is_dir():
        tracks = sorted(
            path.resolve()
            for extension in ("mp3", "wav", "ogg")
            for path in package_root.glob(
                f"*_{doc_id}_{page_name}_track_*.{extension}"
            )
        )

    outputs_root = (project_root.resolve() / "outputs").resolve()
    nested_page = outputs_root / "expert_review_package" / doc_id / page_name
    if audio is None:
        for extension in ("mp3", "wav", "ogg"):
            candidate = (nested_page / f"audio.{extension}").resolve()
            if _is_within(candidate, outputs_root) and candidate.is_file():
                audio = candidate
                break
    if not tracks:
        tracks_dir = (nested_page / "tracks").resolve()
        if _is_within(tracks_dir, outputs_root) and tracks_dir.is_dir():
            tracks = sorted(
                path.resolve()
                for path in tracks_dir.iterdir()
                if path.is_file() and path.suffix.lower() in {".mp3", ".wav", ".ogg"}
            )
    return audio, tracks


def _reported_artifact(
    root: Path,
    row: dict[str, str] | None,
    field: str,
) -> Path | None:
    value = str((row or {}).get(field, "")).strip()
    if not value:
        return None
    candidate = (root / Path(value.replace("\\", "/"))).resolve()
    outputs_root = (root / "outputs").resolve()
    return candidate if _is_within(candidate, outputs_root) and candidate.is_file() else None


def _artifact_paths(
    root: Path,
    doc_id: str,
    page_index: int,
) -> dict[str, Path | None]:
    page_name = f"page_{page_index:03d}"
    candidates = {
        "image": (root / "outputs" / "pages" / doc_id / f"{page_name}.png",),
        "midi": (root / "outputs" / "midi" / doc_id / f"{page_name}.mid",),
        "mxl": (
            root / "outputs" / "omr_300dpi" / doc_id / page_name / f"{page_name}.mxl",
            root / "outputs" / "omr" / doc_id / page_name / f"{page_name}.mxl",
        ),
    }
    allowed_roots = {
        "image": (root / "outputs" / "pages",),
        "midi": (root / "outputs" / "midi",),
        "mxl": (
            root / "outputs" / "omr_300dpi",
            root / "outputs" / "omr",
        ),
    }
    result: dict[str, Path | None] = {}
    for kind, paths in candidates.items():
        result[kind] = None
        for path in paths:
            resolved = path.resolve()
            if not any(
                _is_within(resolved, allowed_root.resolve())
                for allowed_root in allowed_roots[kind]
            ):
                continue
            if resolved.is_file():
                result[kind] = resolved
                break
    return result


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def load_dashboard_data(project_root: Path) -> dict[str, object]:
    """Load inventory, labels, optional reports, and per-document aggregates."""
    root = project_root.resolve()
    inventory = read_csv_rows(root / "data" / "labels" / "document_inventory.csv")
    labels = read_csv_rows(root / "data" / "labels" / "pages_validated_thesis.csv")
    omr_rows = read_csv_rows(root / "outputs" / "reports" / "omr_pipeline_report.csv")
    fallback_rows = read_csv_rows(
        root / "outputs" / "reports" / "omr_400dpi_fallback_report.csv"
    )
    failure_rows = read_csv_rows(
        root / "outputs" / "reports" / "omr_failure_report.csv"
    )
    preprocessing_rows = read_csv_rows(
        root / "outputs" / "reports" / "omr_preprocessing_fallback_report.csv"
    )
    feature_rows = read_csv_rows(root / "outputs" / "reports" / "music_features.csv")

    pages_by_doc: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    type_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    music_counts: Counter[str] = Counter()
    for row in labels:
        doc_id = str(row.get("doc_id", "")).strip()
        page_index = _integer(row.get("page_index"))
        if not doc_id or page_index < 1:
            continue
        page_type = str(row.get("page_type", "")).strip() or "unknown"
        has_music = _integer(row.get("has_music"))
        type_counts[doc_id][page_type] += 1
        music_counts[doc_id] += has_music == 1
        pages_by_doc[doc_id].append(
            {
                **row,
                "page_index": page_index,
                "page_type": page_type,
                "has_music": has_music,
                "label_source": row.get("validation_source", ""),
            }
        )

    omr_by_doc = {row.get("doc_id", ""): row for row in omr_rows}
    fallback_by_page = {
        (row.get("doc_id", ""), _integer(row.get("page_index"))): row
        for row in fallback_rows
    }
    failure_by_page = {
        (row.get("doc_id", ""), _integer(row.get("page_index"))): row
        for row in failure_rows
    }
    preprocessing_by_page: defaultdict[
        tuple[str, int], list[dict[str, str]]
    ] = defaultdict(list)
    for row in preprocessing_rows:
        preprocessing_by_page[
            (row.get("doc_id", ""), _integer(row.get("page_index")))
        ].append(row)
    features_by_page = {
        (row.get("doc_id", ""), _integer(row.get("page_index"))): row
        for row in feature_rows
    }

    documents = []
    document_map: dict[str, dict[str, object]] = {}
    for inventory_row in inventory:
        doc_id = str(inventory_row.get("doc_id", "")).strip()
        omr = omr_by_doc.get(doc_id, {})
        sampled = _integer(omr.get("sampled_pages"))
        success = _integer(omr.get("mxl_generated_pages"))
        recovered_pages = {
            page_index
            for (row_doc_id, page_index), row in fallback_by_page.items()
            if row_doc_id == doc_id
            and _is_recovered(row.get("fallback_400_status"))
        }
        recovered_pages.update(
            page_index
            for (row_doc_id, page_index), rows in preprocessing_by_page.items()
            if row_doc_id == doc_id
            and any(
                _is_recovered(row.get("preprocessing_fallback_status"))
                for row in rows
            )
        )
        counts = {page_type: type_counts[doc_id][page_type] for page_type in PAGE_TYPES}
        document = {
            **inventory_row,
            "pages_count": _integer(inventory_row.get("pages_count")),
            "page_type_counts": counts,
            "music_pages_count": music_counts[doc_id],
            "omr_success_count": success,
            "omr_failure_count": max(sampled - success, 0),
            "fallback_recovered_count": len(recovered_pages),
            "music_features_coverage_count": sum(
                row_doc_id == doc_id for row_doc_id, _ in features_by_page
            ),
        }
        documents.append(document)
        document_map[doc_id] = document

    for doc_id, pages in pages_by_doc.items():
        for page in pages:
            page_index = int(page["page_index"])
            artifacts = _artifact_paths(root, doc_id, page_index)
            primary_mxl_exists = artifacts["mxl"] is not None
            fallback = fallback_by_page.get((doc_id, page_index), {})
            failure = failure_by_page.get((doc_id, page_index), {})
            preprocessing = preprocessing_by_page.get((doc_id, page_index), [])
            recovered_variant = next(
                (
                    row.get("variant", "")
                    for row in preprocessing
                    if _is_recovered(row.get("preprocessing_fallback_status"))
                ),
                "",
            )
            if artifacts["mxl"] is None:
                artifacts["mxl"] = _reported_artifact(
                    root, fallback, "fallback_400_mxl_path"
                )
            if artifacts["midi"] is None:
                artifacts["midi"] = _reported_artifact(
                    root, fallback, "fallback_400_midi_path"
                )
            recovered_preprocessing = next(
                (
                    row
                    for row in preprocessing
                    if _is_recovered(row.get("preprocessing_fallback_status"))
                ),
                None,
            )
            if artifacts["mxl"] is None:
                artifacts["mxl"] = _reported_artifact(
                    root, recovered_preprocessing, "preprocessing_mxl_path"
                )
            if artifacts["midi"] is None:
                artifacts["midi"] = _reported_artifact(
                    root, recovered_preprocessing, "preprocessing_midi_path"
                )
            fallback_status = str(fallback.get("fallback_400_status", "")).strip()
            if recovered_variant:
                fallback_status = f"recovered: {recovered_variant}"
                omr_status = "fallback_recovered"
            elif _is_recovered(fallback_status):
                omr_status = "fallback_recovered"
            elif primary_mxl_exists:
                omr_status = "omr_success"
            elif failure or fallback or preprocessing:
                omr_status = "omr_failed"
            elif page["has_music"] == 1 and page["page_type"] in {"music", "mixed"}:
                omr_status = "not_run"
            else:
                omr_status = "omr_skipped"
            page.update(
                {
                    "has_image": artifacts["image"] is not None,
                    "has_mxl": artifacts["mxl"] is not None,
                    "has_midi": artifacts["midi"] is not None,
                    "omr_status": omr_status,
                    "primary_omr_status": (
                        "success" if primary_mxl_exists else "failed"
                        if failure
                        else "not_run"
                    ),
                    "failure_status": fallback.get("primary_failure_status", "")
                    or failure.get("failure_type", ""),
                    "failure_reason": failure.get("failure_type", "")
                    or fallback.get("fallback_400_error", ""),
                    "fallback_400_status": fallback.get(
                        "fallback_400_status", ""
                    ),
                    "preprocessing_fallback_status": (
                        preprocessing[0].get(
                            "preprocessing_fallback_status", ""
                        )
                        if preprocessing
                        else ""
                    ),
                    "best_preprocessing_variant": recovered_variant,
                    "recovery_status": (
                        "recovered"
                        if omr_status == "fallback_recovered"
                        else "still_failed"
                        if omr_status == "omr_failed"
                        else ""
                    ),
                    "fallback_status": fallback_status
                    or (
                        str(preprocessing[0].get("preprocessing_fallback_status", ""))
                        if preprocessing
                        else ""
                    ),
                    "music_features": _features(
                        features_by_page.get((doc_id, page_index))
                    ),
                    "has_music_features": (
                        (doc_id, page_index) in features_by_page
                    ),
                }
            )
        pages.sort(key=lambda row: int(row["page_index"]))

    documents.sort(key=lambda row: str(row["doc_id"]))
    return {
        "documents": documents,
        "document_map": document_map,
        "pages_by_doc": dict(pages_by_doc),
    }


def load_inbox_overview(project_root: Path) -> dict[str, object]:
    inbox = project_root.resolve() / "data" / "inbox"
    files = sorted(path for path in inbox.iterdir() if path.is_file()) if inbox.is_dir() else []
    pdf_files = [path.name for path in files if path.suffix.lower() == ".pdf"]
    mrc_files = [path.name for path in files if path.suffix.lower() in {".mrc", ".marc"}]

    def doc_key(name: str) -> str:
        digits = "".join(re.findall(r"\d+", Path(name).stem))
        return digits[-11:] if len(digits) >= 9 else Path(name).stem.casefold()

    pairs: defaultdict[str, set[str]] = defaultdict(set)
    for name in pdf_files:
        pairs[doc_key(name)].add("pdf")
    for name in mrc_files:
        pairs[doc_key(name)].add("mrc")
    incomplete = [
        {"key": key, "missing": "MRC" if kinds == {"pdf"} else "PDF"}
        for key, kinds in sorted(pairs.items())
        if kinds != {"pdf", "mrc"}
    ]
    return {
        "files": [path.name for path in files],
        "pdf_files": pdf_files,
        "mrc_files": mrc_files,
        "incomplete_pairs": incomplete,
    }


def available_reports(project_root: Path) -> list[dict[str, str]]:
    root = project_root.resolve()
    return [
        {"key": key, "title": title, "path": relative_path}
        for key, title, relative_path in REPORTS
        if (root / relative_path).is_file()
    ]


def report_path(project_root: Path, key: str) -> Path | None:
    for report_key, _, relative_path in REPORTS:
        if report_key == key:
            candidate = (project_root.resolve() / relative_path).resolve()
            return candidate if candidate.is_file() else None
    return None


def dashboard_artifact_path(
    project_root: Path,
    doc_id: str,
    page_index: int,
    kind: str,
) -> Path | None:
    if not re.fullmatch(r"rsl\d+", doc_id, re.IGNORECASE) or page_index < 1:
        return None
    root = project_root.resolve()
    artifact = _artifact_paths(root, doc_id, page_index).get(kind)
    if artifact is not None or kind == "image":
        return artifact
    fallback = next(
        (
            row
            for row in read_csv_rows(
                root / "outputs" / "reports" / "omr_400dpi_fallback_report.csv"
            )
            if row.get("doc_id") == doc_id
            and _integer(row.get("page_index")) == page_index
        ),
        None,
    )
    field = "fallback_400_midi_path" if kind == "midi" else "fallback_400_mxl_path"
    artifact = _reported_artifact(root, fallback, field)
    if artifact is not None:
        return artifact
    preprocessing = next(
        (
            row
            for row in read_csv_rows(
                root
                / "outputs"
                / "reports"
                / "omr_preprocessing_fallback_report.csv"
            )
            if row.get("doc_id") == doc_id
            and _integer(row.get("page_index")) == page_index
            and _is_recovered(row.get("preprocessing_fallback_status"))
        ),
        None,
    )
    field = "preprocessing_midi_path" if kind == "midi" else "preprocessing_mxl_path"
    return _reported_artifact(root, preprocessing, field)


def load_page_detail(
    project_root: Path,
    db_path: Path,
    package_dir: Path,
    doc_id: str,
    page_index: int,
    reviewer_id: int | None = None,
) -> dict[str, object] | None:
    """Build one robust page view from labels, reports, files, and review DB."""
    dashboard = load_dashboard_data(project_root)
    document = dashboard["document_map"].get(doc_id)
    page = next(
        (
            row
            for row in dashboard["pages_by_doc"].get(doc_id, [])
            if int(row["page_index"]) == page_index
        ),
        None,
    )
    if document is None or page is None:
        return None
    review_item = get_item_by_page(db_path, doc_id, page_index, reviewer_id)
    audio, tracks = _audio_paths(
        project_root,
        package_dir,
        review_item,
        doc_id,
        page_index,
    )
    return {
        "document": document,
        "page": page,
        "review_item": review_item,
        "has_audio": audio is not None,
        "tracks_count": len(tracks),
    }


def dashboard_audio_path(
    project_root: Path,
    db_path: Path,
    package_dir: Path,
    doc_id: str,
    page_index: int,
    track_number: int | None = None,
) -> Path | None:
    """Resolve a protected page audio preview or one separate track."""
    if not re.fullmatch(r"rsl\d+", doc_id, re.IGNORECASE) or page_index < 1:
        return None
    review_item = get_item_by_page(db_path, doc_id, page_index)
    audio, tracks = _audio_paths(
        project_root,
        package_dir,
        review_item,
        doc_id,
        page_index,
    )
    if track_number is None:
        return audio
    if track_number < 1 or track_number > len(tracks):
        return None
    return tracks[track_number - 1]
