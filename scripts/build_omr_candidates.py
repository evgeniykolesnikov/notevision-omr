"""Build a CSV list of validated pages ready for OMR."""

import argparse
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PREPROCESSED_DIR = Path("outputs") / "preprocessed"

OUTPUT_COLUMNS = [
    "doc_id",
    "page_index",
    "page_type",
    "has_music",
    "image_path",
    "preprocessed_path",
    "quality_comment",
    "exists",
]

REQUIRED_COLUMNS = {
    "doc_id",
    "page_index",
    "page_type",
    "has_music",
    "image_path",
}


def build_omr_candidates(
    labels: pd.DataFrame,
    *,
    doc_id: str | None = None,
    limit: int | None = None,
    preprocessed_dir: Path = DEFAULT_PREPROCESSED_DIR,
    project_root: Path = PROJECT_ROOT,
) -> pd.DataFrame:
    """Select validated music pages and build their preprocessed paths."""
    missing = REQUIRED_COLUMNS.difference(labels.columns)
    if missing:
        missing_names = ", ".join(sorted(missing))
        raise ValueError(f"Labels are missing required columns: {missing_names}")
    if limit is not None and limit <= 0:
        raise ValueError(f"limit must be a positive integer, got: {limit}")

    selected = labels[
        (labels["has_music"] == 1)
        & (labels["page_type"].astype(str).str.lower() == "music")
    ].copy()
    if doc_id is not None:
        selected = selected[selected["doc_id"].astype(str) == doc_id]

    selected = selected.sort_values(
        ["doc_id", "page_index"],
        kind="stable",
    )
    if limit is not None:
        selected = selected.head(limit)

    if "quality_comment" not in selected.columns:
        selected["quality_comment"] = ""
    else:
        selected["quality_comment"] = selected["quality_comment"].fillna("")

    preprocessed_paths: list[str] = []
    existence: list[bool] = []
    for page in selected.itertuples(index=False):
        relative_path = (
            preprocessed_dir
            / str(page.doc_id)
            / f"page_{int(page.page_index):03d}_binary.png"
        )
        absolute_path = (
            relative_path
            if relative_path.is_absolute()
            else project_root / relative_path
        )
        preprocessed_paths.append(str(relative_path))
        existence.append(absolute_path.is_file())

    selected["preprocessed_path"] = preprocessed_paths
    selected["exists"] = existence
    return selected[OUTPUT_COLUMNS].reset_index(drop=True)


def write_omr_candidates(
    labels_path: Path,
    output_path: Path,
    *,
    doc_id: str | None = None,
    limit: int | None = None,
    project_root: Path = PROJECT_ROOT,
) -> pd.DataFrame:
    """Read labels and write the OMR candidate CSV."""
    if not labels_path.is_file():
        raise FileNotFoundError(f"Labels file does not exist: {labels_path}")

    labels = pd.read_csv(labels_path, keep_default_na=False)
    candidates = build_omr_candidates(
        labels,
        doc_id=doc_id,
        limit=limit,
        project_root=project_root,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(output_path, index=False)
    return candidates


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--doc-id", help="Include only one document")
    parser.add_argument("--limit", type=int, help="Maximum number of candidates")
    return parser.parse_args()


def main() -> None:
    """Build and save the OMR candidate list."""
    args = parse_args()
    candidates = write_omr_candidates(
        args.labels,
        args.out,
        doc_id=args.doc_id,
        limit=args.limit,
    )
    available = int(candidates["exists"].sum())
    print(f"OMR candidates: {len(candidates)}")
    print(f"Preprocessed images found: {available}")
    print(f"Candidates file: {args.out}")


if __name__ == "__main__":
    main()
