"""Build a local HTML gallery for reviewing page labels."""

import argparse
import html
import os
from pathlib import Path
from urllib.parse import quote

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_COLUMNS = {
    "doc_id",
    "page_index",
    "page_type",
    "has_music",
    "has_music_pred",
    "has_music_score",
    "image_path",
}


def _relative_image_uri(
    image_path: object,
    output_dir: Path,
    project_root: Path,
) -> str:
    source = Path(str(image_path))
    if not source.is_absolute():
        source = project_root / source
    relative = os.path.relpath(source.resolve(), output_dir.resolve())
    return quote(Path(relative).as_posix(), safe="/:._-")


def build_review_gallery_html(
    labels: pd.DataFrame,
    output_path: Path,
    *,
    doc_id: str | None = None,
    uncertain_only: bool = False,
    limit: int | None = None,
    project_root: Path = PROJECT_ROOT,
) -> str:
    """Return an HTML gallery for the selected label rows."""
    missing = REQUIRED_COLUMNS.difference(labels.columns)
    if missing:
        missing_names = ", ".join(sorted(missing))
        raise ValueError(f"Labels are missing required columns: {missing_names}")
    if limit is not None and limit <= 0:
        raise ValueError(f"limit must be a positive integer, got: {limit}")

    selected = labels.copy()
    if doc_id is not None:
        selected = selected[selected["doc_id"].astype(str) == doc_id]
    if uncertain_only:
        scores = pd.to_numeric(selected["has_music_score"], errors="coerce")
        selected = selected[scores.between(0.1, 0.9, inclusive="both")]
    if limit is not None:
        selected = selected.head(limit)

    rows: list[str] = []
    for row in selected.itertuples(index=False):
        image_uri = _relative_image_uri(
            row.image_path,
            output_path.parent,
            project_root,
        )
        cells = [
            f'<td class="thumbnail"><a href="{image_uri}">'
            f'<img src="{image_uri}" alt="Page thumbnail" loading="lazy"></a></td>',
            f"<td>{html.escape(str(row.doc_id))}</td>",
            f"<td>{html.escape(str(row.page_index))}</td>",
            f"<td>{html.escape(str(row.page_type))}</td>",
            f"<td>{html.escape(str(row.has_music))}</td>",
            f"<td>{html.escape(str(row.has_music_pred))}</td>",
            f"<td>{html.escape(str(row.has_music_score))}</td>",
            f"<td><code>{html.escape(str(row.image_path))}</code></td>",
        ]
        rows.append(f"<tr>{''.join(cells)}</tr>")

    table_body = "\n".join(rows)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NoteVision page review</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #202124; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #d5d7da; padding: 8px; text-align: left; }}
    th {{ background: #f3f4f6; position: sticky; top: 0; }}
    tr:nth-child(even) {{ background: #fafafa; }}
    .thumbnail {{ width: 180px; text-align: center; }}
    .thumbnail img {{ max-width: 170px; max-height: 230px; object-fit: contain; }}
    code {{ word-break: break-all; }}
  </style>
</head>
<body>
  <h1>NoteVision page review</h1>
  <p>Pages shown: {len(selected)}</p>
  <table>
    <thead>
      <tr>
        <th>Thumbnail</th>
        <th>doc_id</th>
        <th>page_index</th>
        <th>page_type</th>
        <th>has_music</th>
        <th>has_music_pred</th>
        <th>has_music_score</th>
        <th>image_path</th>
      </tr>
    </thead>
    <tbody>
{table_body}
    </tbody>
  </table>
</body>
</html>
"""


def write_review_gallery(
    labels_path: Path,
    output_path: Path,
    *,
    doc_id: str | None = None,
    uncertain_only: bool = False,
    limit: int | None = None,
    project_root: Path = PROJECT_ROOT,
) -> int:
    """Read labels and write the review gallery, returning its row count."""
    if not labels_path.is_file():
        raise FileNotFoundError(f"Labels file does not exist: {labels_path}")

    labels = pd.read_csv(labels_path, keep_default_na=False)
    gallery = build_review_gallery_html(
        labels,
        output_path,
        doc_id=doc_id,
        uncertain_only=uncertain_only,
        limit=limit,
        project_root=project_root,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(gallery, encoding="utf-8")
    return gallery.count("<tr>") - 1


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--doc-id", help="Show only one document")
    parser.add_argument(
        "--uncertain-only",
        action="store_true",
        help="Show pages with scores between 0.1 and 0.9",
    )
    parser.add_argument("--limit", type=int, help="Maximum number of pages")
    return parser.parse_args()


def main() -> None:
    """Build the gallery and print its path."""
    args = parse_args()
    page_count = write_review_gallery(
        args.labels,
        args.out,
        doc_id=args.doc_id,
        uncertain_only=args.uncertain_only,
        limit=args.limit,
    )
    print(f"Pages shown: {page_count}")
    print(f"Review gallery: {args.out}")


if __name__ == "__main__":
    main()
