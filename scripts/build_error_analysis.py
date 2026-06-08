"""Build a page-level detector error report and local review gallery."""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
from pathlib import Path

ERROR_COLUMNS = [
    "doc_id",
    "page_index",
    "image_path",
    "has_music",
    "has_music_pred",
    "has_music_score",
    "error_type",
]
REQUIRED_COLUMNS = set(ERROR_COLUMNS) - {"error_type"}


def _binary(row: dict[str, str], column: str) -> int:
    value = row.get(column, "").strip()
    try:
        parsed = int(float(value))
    except ValueError as error:
        raise ValueError(f"{column} must contain only 0 or 1; got {value!r}") from error
    if parsed not in {0, 1}:
        raise ValueError(f"{column} must contain only 0 or 1; got {value!r}")
    return parsed


def _score(row: dict[str, str]) -> float:
    value = row.get("has_music_score", "").strip()
    try:
        return float(value)
    except ValueError as error:
        raise ValueError(f"Invalid has_music_score value: {value!r}") from error


def build_error_rows(
    labels_rows: list[dict[str, str]],
) -> list[dict[str, str | int | float]]:
    """Return one normalized row for every false positive or false negative."""
    errors: list[dict[str, str | int | float]] = []
    for row in labels_rows:
        actual = _binary(row, "has_music")
        predicted = _binary(row, "has_music_pred")
        if actual == predicted:
            continue
        errors.append(
            {
                "doc_id": row.get("doc_id", "").strip(),
                "page_index": int(float(row.get("page_index", "0"))),
                "image_path": row.get("image_path", "").strip(),
                "has_music": actual,
                "has_music_pred": predicted,
                "has_music_score": _score(row),
                "error_type": (
                    "false_positive" if predicted == 1 else "false_negative"
                ),
            }
        )
    return sorted(
        errors,
        key=lambda row: (
            str(row["doc_id"]),
            int(row["page_index"]),
        ),
    )


def read_labels(path: Path) -> list[dict[str, str]]:
    """Read labels and validate all fields needed by the error report."""
    if not path.is_file():
        raise FileNotFoundError(f"Labels CSV does not exist: {path}")
    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        missing = sorted(REQUIRED_COLUMNS - set(reader.fieldnames or []))
        if missing:
            raise ValueError(
                "Labels CSV is missing required columns: " + ", ".join(missing)
            )
        return list(reader)


def write_error_analysis(
    labels_path: Path,
    output_path: Path,
) -> list[dict[str, str | int | float]]:
    """Build and save the page-level detector error CSV."""
    errors = build_error_rows(read_labels(labels_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=ERROR_COLUMNS)
        writer.writeheader()
        writer.writerows(errors)
    return errors


def _gallery_image(
    image_path: str,
    gallery_path: Path,
    project_root: Path,
) -> tuple[str, bool]:
    source = Path(image_path.replace("\\", os.sep))
    absolute_source = source if source.is_absolute() else project_root / source
    relative = os.path.relpath(absolute_source, gallery_path.parent)
    return Path(relative).as_posix(), absolute_source.is_file()


def build_error_gallery_html(
    error_rows: list[dict[str, str | int | float]],
    gallery_path: Path,
    project_root: Path | None = None,
) -> str:
    """Render a static gallery with error-type filters and score sorting."""
    root = (project_root or Path.cwd()).resolve()
    cards = []
    for row in error_rows:
        image_src, image_exists = _gallery_image(
            str(row["image_path"]),
            gallery_path.resolve(),
            root,
        )
        error_type = str(row["error_type"])
        warning = (
            ""
            if image_exists
            else '<p class="warning">Image file was not found.</p>'
        )
        cards.append(
            f"""
            <article class="card" data-error-type="{html.escape(error_type)}"
                     data-score="{float(row['has_music_score']):.10f}">
              <div class="image-wrap">
                <img src="{html.escape(image_src, quote=True)}"
                     alt="{html.escape(str(row['doc_id']))} page {row['page_index']}"
                     loading="lazy">
                {warning}
              </div>
              <div class="details">
                <span class="badge">{html.escape(error_type.replace('_', ' '))}</span>
                <h2>{html.escape(str(row['doc_id']))} / page_{int(row['page_index']):03d}</h2>
                <dl>
                  <dt>Ground truth</dt><dd>{int(row['has_music'])}</dd>
                  <dt>Prediction</dt><dd>{int(row['has_music_pred'])}</dd>
                  <dt>Confidence score</dt><dd>{float(row['has_music_score']):.4f}</dd>
                  <dt>Image</dt><dd>{html.escape(str(row['image_path']))}</dd>
                </dl>
              </div>
            </article>
            """
        )

    data_summary = json.dumps(
        {
            "total": len(error_rows),
            "false_positive": sum(
                row["error_type"] == "false_positive" for row in error_rows
            ),
            "false_negative": sum(
                row["error_type"] == "false_negative" for row in error_rows
            ),
        }
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Music Detector Error Gallery</title>
  <style>
    :root {{ color-scheme: light; font-family: Arial, sans-serif; }}
    body {{ margin: 0; background: #f3f4f6; color: #172033; }}
    header {{ position: sticky; top: 0; z-index: 2; padding: 18px 24px;
      background: #ffffffee; border-bottom: 1px solid #d8dce5; }}
    h1 {{ margin: 0 0 12px; font-size: 24px; }}
    .controls {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
    button, select {{ padding: 8px 12px; border: 1px solid #aeb6c5;
      border-radius: 6px; background: white; cursor: pointer; }}
    button.active {{ background: #172033; color: white; }}
    #summary {{ margin-left: auto; color: #596174; }}
    main {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(330px, 1fr));
      gap: 18px; padding: 24px; }}
    .card {{ overflow: hidden; background: white; border: 1px solid #d8dce5;
      border-radius: 10px; box-shadow: 0 3px 12px #17203312; }}
    .image-wrap {{ min-height: 260px; display: grid; place-items: center;
      padding: 12px; background: #e7e9ef; }}
    img {{ max-width: 100%; height: 360px; object-fit: contain; background: white; }}
    .details {{ padding: 14px 16px 18px; }}
    .details h2 {{ margin: 9px 0 12px; font-size: 17px; }}
    .badge {{ padding: 4px 8px; border-radius: 999px; background: #ffe0df;
      color: #8a2520; font-size: 12px; font-weight: bold; }}
    dl {{ display: grid; grid-template-columns: 130px 1fr; gap: 6px 10px; margin: 0; }}
    dt {{ color: #687084; }} dd {{ margin: 0; overflow-wrap: anywhere; }}
    .warning {{ color: #a33a22; font-weight: bold; }}
  </style>
</head>
<body>
  <header>
    <h1>Music Detector Error Gallery</h1>
    <div class="controls">
      <button class="filter active" data-filter="all">All errors</button>
      <button class="filter" data-filter="false_positive">False positives</button>
      <button class="filter" data-filter="false_negative">False negatives</button>
      <label for="sort">Sort by confidence:</label>
      <select id="sort">
        <option value="desc">Highest score first</option>
        <option value="asc">Lowest score first</option>
      </select>
      <span id="summary"></span>
    </div>
  </header>
  <main id="gallery">
    {''.join(cards)}
  </main>
  <script>
    const totals = {data_summary};
    const gallery = document.getElementById("gallery");
    const cards = [...gallery.querySelectorAll(".card")];
    let currentFilter = "all";

    function render() {{
      const direction = document.getElementById("sort").value === "asc" ? 1 : -1;
      cards.sort((a, b) => direction * (Number(a.dataset.score) - Number(b.dataset.score)));
      let visible = 0;
      cards.forEach((card) => {{
        const show = currentFilter === "all" || card.dataset.errorType === currentFilter;
        card.hidden = !show;
        gallery.appendChild(card);
        if (show) visible += 1;
      }});
      document.getElementById("summary").textContent =
        `${{visible}} shown / ${{totals.total}} errors`;
    }}

    document.querySelectorAll(".filter").forEach((button) => {{
      button.addEventListener("click", () => {{
        currentFilter = button.dataset.filter;
        document.querySelectorAll(".filter").forEach((item) =>
          item.classList.toggle("active", item === button));
        render();
      }});
    }});
    document.getElementById("sort").addEventListener("change", render);
    render();
  </script>
</body>
</html>
"""


def write_error_gallery(
    error_rows: list[dict[str, str | int | float]],
    gallery_path: Path,
    project_root: Path | None = None,
) -> None:
    """Save the local detector error gallery."""
    gallery_path.parent.mkdir(parents=True, exist_ok=True)
    gallery_path.write_text(
        build_error_gallery_html(error_rows, gallery_path, project_root),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--labels",
        type=Path,
        default=Path("data/labels/pages_validated_thesis.csv"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("outputs/reports/error_analysis.csv"),
    )
    parser.add_argument(
        "--gallery-out",
        type=Path,
        default=Path("outputs/reports/error_gallery.html"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        errors = write_error_analysis(args.labels, args.out)
        write_error_gallery(errors, args.gallery_out)
    except (FileNotFoundError, ValueError, OSError, csv.Error) as error:
        raise SystemExit(f"Error: {error}") from error

    false_positives = sum(
        row["error_type"] == "false_positive" for row in errors
    )
    false_negatives = len(errors) - false_positives
    print(f"Errors: {len(errors)}")
    print(f"False positives: {false_positives}")
    print(f"False negatives: {false_negatives}")
    print(f"Report: {args.out}")
    print(f"Gallery: {args.gallery_out}")


if __name__ == "__main__":
    main()
