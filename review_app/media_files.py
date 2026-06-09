"""Safe discovery of downloadable OMR result files for review items."""

from __future__ import annotations

import re
from pathlib import Path

DOC_ID_PATTERN = re.compile(r"^rsl\d+$", re.IGNORECASE)


def _existing_file(
    candidates: list[Path],
    allowed_roots: tuple[Path, ...],
) -> Path | None:
    resolved_roots = tuple(root.resolve() for root in allowed_roots)
    for candidate in candidates:
        resolved = candidate.resolve()
        inside_allowed_root = False
        for root in resolved_roots:
            try:
                resolved.relative_to(root)
                inside_allowed_root = True
                break
            except ValueError:
                continue
        if inside_allowed_root and resolved.is_file():
            return resolved
    return None


def _package_candidates(
    package_dir: Path,
    item: dict[str, object],
    extension: str,
) -> list[Path]:
    scan_name = Path(str(item.get("scan_path", ""))).name
    prefix = (
        scan_name[: -len("_scan.png")]
        if scan_name.lower().endswith("_scan.png")
        else ""
    )
    doc_id = str(item["doc_id"])
    page_name = f"page_{int(item['page_index']):03d}"
    candidates: list[Path] = []
    if prefix:
        suffixes = (
            (f"{prefix}_midi.mid", f"{prefix}.mid")
            if extension == "mid"
            else (
                f"{prefix}_score.mxl",
                f"{prefix}_mxl.mxl",
                f"{prefix}.mxl",
                f"{prefix}.musicxml",
            )
        )
        candidates.extend(package_dir / suffix for suffix in suffixes)
    nested_dir = package_dir / doc_id / page_name
    if extension == "mid":
        candidates.extend((nested_dir / "midi.mid", nested_dir / f"{page_name}.mid"))
    else:
        candidates.extend(
            (
                nested_dir / f"{page_name}.mxl",
                nested_dir / "score.mxl",
                nested_dir / f"{page_name}.musicxml",
            )
        )
    return candidates


def find_review_result_file(
    item: dict[str, object],
    *,
    kind: str,
    package_dir: Path,
    project_root: Path,
) -> Path | None:
    """Find a MIDI or MXL/MusicXML file without searching outside known roots."""
    if kind not in {"midi", "mxl"}:
        raise ValueError(f"Unsupported review result kind: {kind}")
    doc_id = str(item.get("doc_id", ""))
    if not DOC_ID_PATTERN.fullmatch(doc_id):
        return None
    try:
        page_index = int(item["page_index"])
    except (KeyError, TypeError, ValueError):
        return None
    if page_index < 1:
        return None

    page_name = f"page_{page_index:03d}"
    extension = "mid" if kind == "midi" else "mxl"
    candidates = _package_candidates(
        package_dir.resolve(),
        item,
        extension,
    )

    package_root = package_dir.resolve()
    outputs = project_root.resolve() / "outputs"
    expert_page = outputs / "expert_review_package" / doc_id / page_name
    if kind == "midi":
        candidates.extend(
            (
                expert_page / "midi.mid",
                outputs / "midi" / doc_id / f"{page_name}.mid",
            )
        )
    else:
        candidates.extend(
            (
                expert_page / f"{page_name}.mxl",
                expert_page / "score.mxl",
                outputs / "omr_300dpi" / doc_id / page_name / f"{page_name}.mxl",
                outputs / "omr" / doc_id / page_name / f"{page_name}.mxl",
            )
        )
    return _existing_file(candidates, (package_root, outputs))


def download_filename(item: dict[str, object], kind: str) -> str:
    extension = "mid" if kind == "midi" else "mxl"
    return (
        f"notevision_{item['doc_id']}_"
        f"page_{int(item['page_index']):03d}.{extension}"
    )
