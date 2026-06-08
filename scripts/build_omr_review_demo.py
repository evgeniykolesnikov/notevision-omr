"""Build a static local OMR expert review demo."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LABELS = (
    PROJECT_ROOT / "data" / "labels" / "omr_expert_evaluation_thesis.csv"
)
DEFAULT_MIDI_DIR = PROJECT_ROOT / "outputs" / "midi"
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "outputs" / "reports" / "omr_review_demo.html"
)
REQUIRED_COLUMNS = {
    "doc_id",
    "page_index",
    "image_path",
    "mxl_path",
}


def _resolve_path(path_value: str, project_root: Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else project_root / path


def _relative_uri(path: Path, output_dir: Path) -> str:
    relative = os.path.relpath(path.resolve(), output_dir.resolve())
    return quote(Path(relative).as_posix(), safe="/:._-")


def build_midi_path(
    doc_id: str,
    page_index: int,
    midi_dir: Path,
) -> Path:
    """Build the expected MIDI path for an OMR page."""
    return midi_dir / doc_id / f"page_{page_index:03d}.mid"


def _json_for_script(value: object) -> str:
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _prepare_rows(
    rows: list[dict[str, str]],
    output_path: Path,
    midi_dir: Path,
    project_root: Path,
) -> list[dict[str, object]]:
    prepared: list[dict[str, object]] = []
    for row in rows:
        page_index = int(row["page_index"])
        image_path = _resolve_path(row["image_path"], project_root)
        mxl_path = _resolve_path(row["mxl_path"], project_root)
        midi_path = build_midi_path(
            row["doc_id"],
            page_index,
            midi_dir,
        )
        prepared.append(
            {
                "doc_id": row["doc_id"],
                "page_index": page_index,
                "page_type": row.get("page_type", ""),
                "selection_reason": row.get("selection_reason", ""),
                "has_music_score": row.get("has_music_score", ""),
                "image_path": row["image_path"],
                "image_uri": _relative_uri(image_path, output_path.parent),
                "image_exists": image_path.is_file(),
                "mxl_path": row["mxl_path"],
                "mxl_uri": _relative_uri(mxl_path, output_path.parent),
                "mxl_exists": mxl_path.is_file(),
                "midi_path": str(
                    midi_path.relative_to(project_root)
                    if midi_path.is_relative_to(project_root)
                    else midi_path
                ),
                "midi_uri": _relative_uri(midi_path, output_path.parent),
                "midi_exists": midi_path.is_file(),
            }
        )
    return prepared


def build_omr_review_demo_html(
    rows: list[dict[str, str]],
    output_path: Path,
    *,
    midi_dir: Path = DEFAULT_MIDI_DIR,
    project_root: Path = PROJECT_ROOT,
) -> str:
    """Return a self-contained static OMR review page."""
    prepared = _prepare_rows(
        rows,
        output_path,
        midi_dir,
        project_root,
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NoteVision OMR expert review demo</title>
  <style>
    :root {{ font-family: Arial, sans-serif; color: #17212b; }}
    body {{ margin: 0; background: #eef2f5; }}
    header {{ position: sticky; top: 0; z-index: 5; padding: 16px 22px;
      background: #17212b; color: white; box-shadow: 0 2px 8px #0003; }}
    header h1 {{ margin: 0 0 6px; font-size: 22px; }}
    header p {{ margin: 0; color: #d5dde5; }}
    main {{ display: grid; gap: 20px; padding: 22px; }}
    .review-card {{ display: grid; grid-template-columns: minmax(300px, 46%) 1fr;
      gap: 20px; padding: 18px; background: white; border-radius: 10px;
      box-shadow: 0 2px 8px #1d2a3520; }}
    .scan {{ min-height: 420px; padding: 10px; text-align: center;
      background: #e5e9ed; border-radius: 7px; }}
    .scan img {{ max-width: 100%; max-height: 760px; object-fit: contain; }}
    .warning {{ padding: 12px; color: #a61b1b; font-weight: bold; }}
    h2 {{ margin: 0 0 12px; font-size: 20px; }}
    dl {{ display: grid; grid-template-columns: max-content 1fr;
      gap: 6px 12px; margin: 0 0 14px; }}
    dt {{ font-weight: bold; }}
    dd {{ margin: 0; overflow-wrap: anywhere; }}
    code {{ font-size: 12px; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 9px; margin: 12px 0 18px; }}
    .actions a {{ padding: 9px 12px; color: white; background: #1769aa;
      border-radius: 6px; text-decoration: none; }}
    .actions a.midi {{ background: #087f5b; }}
    .actions a.missing {{ pointer-events: none; background: #8b969f; }}
    .form-grid {{ display: grid; grid-template-columns: repeat(2, minmax(150px, 1fr));
      gap: 12px; }}
    label {{ display: grid; gap: 5px; font-weight: bold; }}
    select, textarea {{ box-sizing: border-box; width: 100%; padding: 8px;
      border: 1px solid #9aa9b5; border-radius: 5px; font: inherit; }}
    textarea {{ min-height: 120px; resize: vertical; }}
    .comment {{ grid-column: 1 / -1; }}
    .saved {{ margin-top: 10px; color: #087f5b; font-size: 13px; }}
    @media (max-width: 850px) {{
      .review-card {{ grid-template-columns: 1fr; }}
      .form-grid {{ grid-template-columns: 1fr; }}
      .comment {{ grid-column: auto; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>NoteVision OMR expert review demo</h1>
    <p>Pages: {len(prepared)}. Ratings are saved locally in this browser.</p>
  </header>
  <main id="reviews"></main>
  <script>
    const pages = {_json_for_script(prepared)};
    const storageKey = 'notevision-omr-review-demo-v1';
    const reviews = document.getElementById('reviews');

    function escapeHtml(value) {{
      const node = document.createElement('div');
      node.textContent = String(value ?? '');
      return node.innerHTML;
    }}

    function loadState() {{
      try {{
        return JSON.parse(localStorage.getItem(storageKey) || '{{}}');
      }} catch (error) {{
        console.warn('Could not restore OMR review', error);
        return {{}};
      }}
    }}

    const state = loadState();
    function key(page) {{
      return `${{page.doc_id}}::${{page.page_index}}`;
    }}

    function options(values, selected) {{
      return values.map(value =>
        `<option value="${{escapeHtml(value)}}" ${{String(value) === String(selected) ? 'selected' : ''}}>`
        + `${{escapeHtml(value)}}</option>`).join('');
    }}

    function action(uri, exists, label, className = '') {{
      return `<a class="${{className}} ${{exists ? '' : 'missing'}}"
        href="${{escapeHtml(uri)}}" target="_blank">${{escapeHtml(label)}}
        ${{exists ? '' : ' (missing)'}}</a>`;
    }}

    function card(page) {{
      const saved = state[key(page)] || {{}};
      const imageWarning = page.image_exists
        ? ''
        : '<div class="warning">PNG file was not found. Metadata is still available.</div>';
      return `
        <article class="review-card" data-key="${{escapeHtml(key(page))}}">
          <section class="scan">
            <a href="${{escapeHtml(page.image_uri)}}" target="_blank">
              <img src="${{escapeHtml(page.image_uri)}}"
                alt="${{escapeHtml(page.doc_id)}} page ${{page.page_index}}"
                loading="lazy">
            </a>
            ${{imageWarning}}
          </section>
          <section>
            <h2>${{escapeHtml(page.doc_id)}} / page ${{page.page_index}}</h2>
            <dl>
              <dt>Document</dt><dd>${{escapeHtml(page.doc_id)}}</dd>
              <dt>Page</dt><dd>${{page.page_index}}</dd>
              <dt>Page type</dt><dd>${{escapeHtml(page.page_type)}}</dd>
              <dt>Selection</dt><dd>${{escapeHtml(page.selection_reason)}}</dd>
              <dt>Detector score</dt><dd>${{escapeHtml(page.has_music_score)}}</dd>
              <dt>PNG</dt><dd><code>${{escapeHtml(page.image_path)}}</code></dd>
              <dt>MXL</dt><dd><code>${{escapeHtml(page.mxl_path)}}</code></dd>
              <dt>MIDI</dt><dd><code>${{escapeHtml(page.midi_path)}}</code></dd>
            </dl>
            <div class="actions">
              ${{action(page.mxl_uri, page.mxl_exists, 'Open MXL')}}
              ${{action(page.midi_uri, page.midi_exists, 'Open MIDI', 'midi')}}
            </div>
            <div class="form-grid">
              <label>Usable
                <select data-field="usable">
                  ${{options(['', 'yes', 'partial', 'no'], saved.usable || '')}}
                </select>
              </label>
              <label>Pitch quality (1-5)
                <select data-field="pitch_quality">
                  ${{options(['', 1, 2, 3, 4, 5], saved.pitch_quality || '')}}
                </select>
              </label>
              <label>Duration quality (1-5)
                <select data-field="duration_quality">
                  ${{options(['', 1, 2, 3, 4, 5], saved.duration_quality || '')}}
                </select>
              </label>
              <label>Overall quality (1-5)
                <select data-field="overall_quality">
                  ${{options(['', 1, 2, 3, 4, 5], saved.overall_quality || '')}}
                </select>
              </label>
              <label class="comment">Expert comments
                <textarea data-field="expert_comment">${{escapeHtml(saved.expert_comment || '')}}</textarea>
              </label>
            </div>
            <div class="saved">Changes are saved locally.</div>
          </section>
        </article>`;
    }}

    reviews.innerHTML = pages.map(card).join('');
    reviews.querySelectorAll('.review-card').forEach(cardNode => {{
      cardNode.querySelectorAll('[data-field]').forEach(field => {{
        field.addEventListener('input', () => {{
          const pageState = state[cardNode.dataset.key] || {{}};
          pageState[field.dataset.field] = field.value;
          state[cardNode.dataset.key] = pageState;
          localStorage.setItem(storageKey, JSON.stringify(state));
        }});
      }});
    }});
  </script>
</body>
</html>
"""


def write_omr_review_demo(
    labels_path: Path,
    output_path: Path,
    *,
    midi_dir: Path = DEFAULT_MIDI_DIR,
    project_root: Path = PROJECT_ROOT,
    limit: int | None = None,
) -> int:
    """Read expert sample rows and write the static review demo."""
    if not labels_path.is_file():
        raise FileNotFoundError(f"Labels CSV does not exist: {labels_path}")
    if limit is not None and limit <= 0:
        raise ValueError(f"limit must be a positive integer, got: {limit}")

    with labels_path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS.difference(columns)
        if missing:
            names = ", ".join(sorted(missing))
            raise ValueError(f"Labels CSV is missing required columns: {names}")
        rows = list(reader)

    if limit is not None:
        rows = rows[:limit]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        build_omr_review_demo_html(
            rows,
            output_path,
            midi_dir=midi_dir,
            project_root=project_root,
        ),
        encoding="utf-8",
    )
    return len(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--midi-dir", type=Path, default=DEFAULT_MIDI_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        count = write_omr_review_demo(
            args.labels,
            args.out,
            midi_dir=args.midi_dir,
            limit=args.limit,
        )
    except (FileNotFoundError, ValueError, OSError) as error:
        raise SystemExit(f"Error: {error}") from error
    print(f"Pages: {count}")
    print(f"OMR review demo: {args.out}")


if __name__ == "__main__":
    main()
