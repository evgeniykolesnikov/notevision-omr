"""Build a static HTML gallery for visual review of OMR pipeline failures."""

from __future__ import annotations

import argparse
import csv
import html
import os
from pathlib import Path
from urllib.parse import quote

REQUIRED_COLUMNS = {
    "doc_id",
    "page_index",
    "image_path",
    "has_mxl",
    "has_midi",
    "failure_type",
}


def read_failure_rows(path: Path) -> list[dict[str, str]]:
    """Read and validate the page-level OMR failure report."""
    if not path.is_file():
        raise FileNotFoundError(f"OMR failure report does not exist: {path}")
    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        missing = sorted(REQUIRED_COLUMNS - set(reader.fieldnames or []))
        if missing:
            raise ValueError(
                "OMR failure report is missing required columns: "
                + ", ".join(missing)
            )
        return list(reader)


def _relative_image_uri(
    image_path: str,
    output_path: Path,
    project_root: Path,
) -> tuple[str, bool]:
    source = Path(image_path.replace("\\", os.sep))
    if not source.is_absolute():
        source = project_root / source
    relative = os.path.relpath(source.resolve(), output_path.parent.resolve())
    return quote(Path(relative).as_posix(), safe="/:._-"), source.is_file()


def build_omr_failure_gallery_html(
    failure_rows: list[dict[str, object]],
    output_path: Path,
    *,
    project_root: Path | None = None,
) -> str:
    """Render failure cards with stage filters and local page images."""
    root = (project_root or Path.cwd()).resolve()
    cards: list[str] = []
    for row in failure_rows:
        image_uri, image_exists = _relative_image_uri(
            str(row.get("image_path", "")),
            output_path,
            root,
        )
        failure_type = str(row["failure_type"])
        warning = (
            ""
            if image_exists
            else '<p class="warning">Image file was not found.</p>'
        )
        cards.append(
            f"""
            <article class="card" data-failure="{html.escape(failure_type)}">
              <div class="image-wrap">
                <img src="{html.escape(image_uri, quote=True)}"
                     alt="{html.escape(str(row['doc_id']))} page {row['page_index']}"
                     loading="lazy">
                {warning}
              </div>
              <div class="details">
                <span class="badge">{html.escape(failure_type)}</span>
                <h2>{html.escape(str(row['doc_id']))} /
                    page_{int(row['page_index']):03d}</h2>
                <p>MXL: <strong>{html.escape(str(row['has_mxl']))}</strong></p>
                <p>MIDI: <strong>{html.escape(str(row['has_midi']))}</strong></p>
                <p><code>{html.escape(str(row.get('image_path', '')))}</code></p>
              </div>
            </article>
            """
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OMR Failure Gallery</title>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; background: #f3f4f6;
      color: #172033; }}
    header {{ position: sticky; top: 0; z-index: 2; padding: 18px 24px;
      background: #ffffffee; border-bottom: 1px solid #d8dce5; }}
    h1 {{ margin: 0 0 12px; }}
    button {{ margin-right: 8px; padding: 8px 12px; border: 1px solid #aeb6c5;
      border-radius: 6px; background: white; cursor: pointer; }}
    button.active {{ background: #172033; color: white; }}
    main {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(330px, 1fr));
      gap: 18px; padding: 24px; }}
    .card {{ overflow: hidden; background: white; border: 1px solid #d8dce5;
      border-radius: 10px; }}
    .image-wrap {{ min-height: 260px; display: grid; place-items: center;
      padding: 12px; background: #e7e9ef; }}
    img {{ max-width: 100%; height: 360px; object-fit: contain; background: white; }}
    .details {{ padding: 14px 16px 18px; }}
    .details h2 {{ font-size: 17px; }}
    .badge {{ padding: 4px 8px; border-radius: 999px; background: #ffe0df;
      color: #8a2520; font-size: 12px; font-weight: bold; }}
    code {{ overflow-wrap: anywhere; }}
    .warning {{ color: #a33a22; font-weight: bold; }}
  </style>
</head>
<body>
  <header>
    <h1>OMR Failure Gallery</h1>
    <button class="filter active" data-filter="all">All failures</button>
    <button class="filter" data-filter="missing_mxl">Missing MXL</button>
    <button class="filter" data-filter="missing_midi">Missing MIDI</button>
    <span id="count"></span>
  </header>
  <main id="gallery">{''.join(cards)}</main>
  <script>
    const cards = [...document.querySelectorAll(".card")];
    function filterCards(value) {{
      let visible = 0;
      cards.forEach((card) => {{
        const show = value === "all" || card.dataset.failure === value;
        card.hidden = !show;
        if (show) visible += 1;
      }});
      document.getElementById("count").textContent = `${{visible}} shown`;
    }}
    document.querySelectorAll(".filter").forEach((button) => {{
      button.addEventListener("click", () => {{
        document.querySelectorAll(".filter").forEach((item) =>
          item.classList.toggle("active", item === button));
        filterCards(button.dataset.filter);
      }});
    }});
    filterCards("all");
  </script>
</body>
</html>
"""


def write_omr_failure_gallery(
    failure_path: Path,
    output_path: Path,
    *,
    project_root: Path | None = None,
) -> int:
    """Read failure rows and save the local HTML gallery."""
    rows = read_failure_rows(failure_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        build_omr_failure_gallery_html(
            rows,
            output_path,
            project_root=project_root,
        ),
        encoding="utf-8",
    )
    return len(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--failures",
        type=Path,
        default=Path("outputs/reports/omr_failure_report.csv"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("outputs/reports/omr_failure_gallery.html"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        count = write_omr_failure_gallery(args.failures, args.out)
    except (FileNotFoundError, ValueError, OSError, csv.Error) as error:
        raise SystemExit(f"Error: {error}") from error
    print(f"Failure pages: {count}")
    print(f"Gallery: {args.out}")


if __name__ == "__main__":
    main()
