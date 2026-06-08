"""Build a static editable HTML gallery for manual label review."""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
from pathlib import Path
from urllib.parse import quote

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PAGE_TYPES = ["music", "title", "text", "blank", "unknown", "mixed", "bad_scan"]
REQUIRED_COLUMNS = [
    "doc_id",
    "page_index",
    "image_path",
    "page_type",
    "has_music",
    "has_music_pred",
    "has_music_score",
    "validation_source",
    "needs_review",
    "review_reason",
    "priority_group",
    "quality_comment",
]


def _relative_image_uri(
    image_path: str,
    output_dir: Path,
    project_root: Path,
) -> tuple[str, bool]:
    source = Path(image_path)
    if not source.is_absolute():
        source = project_root / source
    relative = os.path.relpath(source.resolve(), output_dir.resolve())
    return quote(Path(relative).as_posix(), safe="/:._-"), source.is_file()


def _json_for_script(value: object) -> str:
    """Serialize JSON without allowing values to terminate the script tag."""
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
    project_root: Path,
) -> list[dict[str, object]]:
    prepared: list[dict[str, object]] = []
    for row in rows:
        image_uri, image_exists = _relative_image_uri(
            row["image_path"],
            output_path.parent,
            project_root,
        )
        try:
            uncertain = 0.1 <= float(row["has_music_score"]) <= 0.9
        except ValueError:
            uncertain = True
        priority_groups = set(row["priority_group"].split(";"))
        prepared.append(
            {
                **row,
                "image_uri": image_uri,
                "image_exists": image_exists,
                "is_unknown": row["page_type"] == "unknown",
                "is_uncertain": uncertain,
                "is_boundary": "boundary_pages" in priority_groups,
                "is_random": "random_confident_music" in priority_groups,
            }
        )
    return prepared


def build_editable_review_gallery_html(
    rows: list[dict[str, str]],
    output_path: Path,
    *,
    project_root: Path = PROJECT_ROOT,
) -> str:
    """Return a paginated static editable review gallery."""
    prepared_rows = _prepare_rows(rows, output_path, project_root)
    documents = sorted({str(row["doc_id"]) for row in prepared_rows})
    document_options = "".join(
        f'<option value="{html.escape(doc_id, quote=True)}">'
        f"{html.escape(doc_id)}</option>"
        for doc_id in documents
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NoteVision editable thesis review</title>
  <style>
    :root {{ color-scheme: light; font-family: Arial, sans-serif; }}
    body {{ margin: 0; background: #f4f6f8; color: #1f2933; }}
    header {{ position: sticky; top: 0; z-index: 10; padding: 14px 20px;
      background: #fff; border-bottom: 1px solid #d9e2ec; }}
    h1 {{ margin: 0 0 10px; font-size: 22px; }}
    .toolbar, .pagination {{ display: flex; flex-wrap: wrap; gap: 8px;
      align-items: center; }}
    .pagination {{ margin-top: 9px; }}
    button, select {{ padding: 8px 10px; border: 1px solid #9fb3c8;
      border-radius: 6px; background: #fff; cursor: pointer; }}
    button.active {{ background: #1d4ed8; color: #fff; border-color: #1d4ed8; }}
    .export {{ background: #087f5b; color: #fff; }}
    #counter, #page-info {{ font-weight: bold; }}
    main {{ display: grid; gap: 16px; padding: 20px; }}
    .page-card {{ display: grid; grid-template-columns: minmax(220px, 34%) 1fr;
      gap: 18px; padding: 16px; background: #fff; border: 1px solid #d9e2ec;
      border-radius: 9px; box-shadow: 0 1px 3px rgb(0 0 0 / 8%); }}
    .page-card.changed-card {{ border: 2px solid #087f5b; }}
    .page-image {{ min-height: 220px; text-align: center; background: #eef2f6;
      padding: 8px; border-radius: 6px; }}
    .page-image img {{ max-width: 100%; max-height: 600px; object-fit: contain; }}
    .image-warning {{ padding: 12px; color: #b42318; font-weight: bold; }}
    h2 {{ margin-top: 0; font-size: 18px; }}
    dl {{ display: grid; grid-template-columns: max-content 1fr; gap: 5px 12px; }}
    dt {{ font-weight: bold; }}
    dd {{ margin: 0; overflow-wrap: anywhere; }}
    .quick-actions {{ display: flex; flex-wrap: wrap; gap: 7px; margin: 12px 0; }}
    .quick-actions button {{ background: #e9f2ff; }}
    .edit-fields {{ display: grid; gap: 10px; margin-top: 10px; }}
    label {{ display: grid; gap: 4px; font-weight: bold; }}
    .edit-fields select, textarea {{ width: 100%; box-sizing: border-box;
      padding: 7px; border: 1px solid #9fb3c8; border-radius: 5px;
      font: inherit; }}
    .changed-badge {{ display: none; width: fit-content; padding: 4px 8px;
      border-radius: 999px; color: #065f46; background: #d1fae5;
      font-weight: bold; }}
    .changed-card .changed-badge {{ display: inline-block; }}
    .empty-state {{ padding: 35px; text-align: center; background: #fff;
      border-radius: 8px; }}
    @media (max-width: 760px) {{
      .page-card {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>NoteVision editable thesis review</h1>
    <div class="toolbar">
      <button class="filter active" data-filter="all">Show all</button>
      <button class="filter" data-filter="unknown">Show unknown</button>
      <button class="filter" data-filter="uncertain">Show uncertain</button>
      <button class="filter" data-filter="boundary">Show boundary_pages</button>
      <button class="filter" data-filter="random">Show random_confident_music</button>
      <button class="filter" data-filter="changed">Show changed only</button>
      <label>Document
        <select id="document-filter">
          <option value="">All documents</option>
          {document_options}
        </select>
      </label>
      <button class="export" id="export-csv">Export corrections CSV</button>
      <button class="export" id="export-json">Export JSON</button>
    </div>
    <div class="pagination">
      <label>Pages
        <select id="page-size">
          <option value="50">50</option>
          <option value="100">100</option>
          <option value="200">200</option>
          <option value="all">All pages</option>
        </select>
      </label>
      <button id="previous-page">Previous</button>
      <button id="next-page">Next</button>
      <span id="page-info"></span>
      <span id="counter"></span>
    </div>
  </header>
  <main id="gallery"></main>
  <script>
    const sourceRows = {_json_for_script(prepared_rows)};
    const pageTypes = {_json_for_script(PAGE_TYPES)};
    const storageKey = 'notevision-thesis-label-review-v2';
    const gallery = document.getElementById('gallery');
    const documentFilter = document.getElementById('document-filter');
    const pageSizeSelect = document.getElementById('page-size');
    const pageInfo = document.getElementById('page-info');
    const counter = document.getElementById('counter');
    let activeFilter = 'all';
    let currentPage = 1;

    function rowKey(row) {{
      return `${{row.doc_id}}::${{row.page_index}}`;
    }}

    function loadSavedState() {{
      try {{
        return JSON.parse(localStorage.getItem(storageKey) || '{{}}');
      }} catch (error) {{
        console.warn('Could not restore saved labels', error);
        return {{}};
      }}
    }}

    const savedState = loadSavedState();
    const states = new Map(sourceRows.map(row => {{
      const saved = savedState[rowKey(row)] || {{}};
      return [rowKey(row), {{
        page_type: saved.page_type ?? row.page_type,
        has_music: String(saved.has_music ?? row.has_music),
        quality_comment: saved.quality_comment ?? row.quality_comment,
        changed: Boolean(saved.changed)
      }}];
    }}));

    function saveState() {{
      const value = {{}};
      states.forEach((state, key) => {{
        if (state.changed) value[key] = state;
      }});
      try {{
        localStorage.setItem(storageKey, JSON.stringify(value));
      }} catch (error) {{
        console.warn('Could not autosave labels', error);
      }}
    }}

    function escapeHtml(value) {{
      const element = document.createElement('div');
      element.textContent = String(value ?? '');
      return element.innerHTML;
    }}

    function matchesFilter(row) {{
      const state = states.get(rowKey(row));
      if (documentFilter.value && row.doc_id !== documentFilter.value) return false;
      if (activeFilter === 'changed') return state.changed;
      if (activeFilter === 'unknown') return state.page_type === 'unknown';
      if (activeFilter === 'uncertain') return row.is_uncertain;
      if (activeFilter === 'boundary') return row.is_boundary;
      if (activeFilter === 'random') return row.is_random;
      return true;
    }}

    function filteredRows() {{
      return sourceRows.filter(matchesFilter);
    }}

    function pageSize(total) {{
      return pageSizeSelect.value === 'all'
        ? Math.max(total, 1)
        : Number(pageSizeSelect.value);
    }}

    function options(values, selected) {{
      return values.map(value =>
        `<option value="${{escapeHtml(value)}}" ${{value === selected ? 'selected' : ''}}>`
        + `${{escapeHtml(value)}}</option>`).join('');
    }}

    function metadata(label, value, code = false) {{
      const content = code
        ? `<code>${{escapeHtml(value)}}</code>`
        : escapeHtml(value);
      return `<dt>${{escapeHtml(label)}}</dt><dd>${{content}}</dd>`;
    }}

    function cardHtml(row) {{
      const state = states.get(rowKey(row));
      const missing = row.image_exists
        ? ''
        : '<div class="image-warning">Image file not found</div>';
      return `
        <article class="page-card ${{state.changed ? 'changed-card' : ''}}"
          data-key="${{escapeHtml(rowKey(row))}}">
          <div class="page-image">
            <a href="${{escapeHtml(row.image_uri)}}" target="_blank">
              <img src="${{escapeHtml(row.image_uri)}}"
                alt="Page ${{escapeHtml(row.page_index)}}" loading="lazy"
                onerror="this.hidden=true;this.parentElement.nextElementSibling.hidden=false">
            </a>
            <div class="image-warning" hidden>Image could not be loaded</div>
            ${{missing}}
          </div>
          <div class="page-content">
            <h2>${{escapeHtml(row.doc_id)}} / page ${{escapeHtml(row.page_index)}}</h2>
            <span class="changed-badge">Changed and autosaved</span>
            <dl>
              ${{metadata('doc_id', row.doc_id)}}
              ${{metadata('page_index', row.page_index)}}
              ${{metadata('image_path', row.image_path, true)}}
              ${{metadata('has_music_pred', row.has_music_pred)}}
              ${{metadata('has_music_score', row.has_music_score)}}
              ${{metadata('validation_source', row.validation_source)}}
              ${{metadata('needs_review', row.needs_review)}}
              ${{metadata('review_reason', row.review_reason)}}
              ${{metadata('priority_group', row.priority_group)}}
            </dl>
            <div class="quick-actions">
              <button data-type="music" data-music="1">Music</button>
              <button data-type="title" data-music="0">Title</button>
              <button data-type="text" data-music="0">Text</button>
              <button data-type="blank" data-music="0">Blank</button>
              <button data-type="bad_scan" data-music="0">Bad Scan</button>
            </div>
            <div class="edit-fields">
              <label>page_type
                <select class="page-type">${{options(pageTypes, state.page_type)}}</select>
              </label>
              <label>has_music
                <select class="has-music">${{options(['1', '0'], state.has_music)}}</select>
              </label>
              <label>quality_comment
                <textarea class="quality-comment" rows="3">${{escapeHtml(state.quality_comment)}}</textarea>
              </label>
            </div>
          </div>
        </article>`;
    }}

    function markChanged(card, update) {{
      const state = states.get(card.dataset.key);
      Object.assign(state, update, {{ changed: true }});
      card.classList.add('changed-card');
      saveState();
      if (activeFilter === 'changed') render();
    }}

    function bindCard(card) {{
      const typeSelect = card.querySelector('.page-type');
      const musicSelect = card.querySelector('.has-music');
      const comment = card.querySelector('.quality-comment');
      typeSelect.addEventListener('change', () =>
        markChanged(card, {{ page_type: typeSelect.value }}));
      musicSelect.addEventListener('change', () =>
        markChanged(card, {{ has_music: musicSelect.value }}));
      comment.addEventListener('input', () =>
        markChanged(card, {{ quality_comment: comment.value }}));
      card.querySelectorAll('.quick-actions button').forEach(button => {{
        button.addEventListener('click', () => {{
          typeSelect.value = button.dataset.type;
          musicSelect.value = button.dataset.music;
          markChanged(card, {{
            page_type: button.dataset.type,
            has_music: button.dataset.music
          }});
        }});
      }});
    }}

    function render() {{
      const rows = filteredRows();
      const size = pageSize(rows.length);
      const pageCount = Math.max(1, Math.ceil(rows.length / size));
      currentPage = Math.min(Math.max(currentPage, 1), pageCount);
      const start = (currentPage - 1) * size;
      const visible = rows.slice(start, start + size);
      gallery.innerHTML = visible.length
        ? visible.map(cardHtml).join('')
        : '<div class="empty-state">No pages match the current filters.</div>';
      gallery.querySelectorAll('.page-card').forEach(bindCard);
      pageInfo.textContent = `Page ${{currentPage}} / ${{pageCount}}`;
      counter.textContent = `Showing ${{visible.length}} of ${{rows.length}} pages`;
      document.getElementById('previous-page').disabled = currentPage <= 1;
      document.getElementById('next-page').disabled = currentPage >= pageCount;
    }}

    document.querySelectorAll('.filter').forEach(button => {{
      button.addEventListener('click', () => {{
        activeFilter = button.dataset.filter;
        currentPage = 1;
        document.querySelectorAll('.filter').forEach(item =>
          item.classList.toggle('active', item === button));
        render();
      }});
    }});
    documentFilter.addEventListener('change', () => {{
      currentPage = 1;
      render();
    }});
    pageSizeSelect.addEventListener('change', () => {{
      currentPage = 1;
      render();
    }});
    document.getElementById('previous-page').addEventListener('click', () => {{
      currentPage -= 1;
      render();
      window.scrollTo({{ top: 0, behavior: 'smooth' }});
    }});
    document.getElementById('next-page').addEventListener('click', () => {{
      currentPage += 1;
      render();
      window.scrollTo({{ top: 0, behavior: 'smooth' }});
    }});

    function changedRows() {{
      return sourceRows.filter(row => states.get(rowKey(row)).changed);
    }}

    function download(content, filename, mimeType) {{
      const blob = new Blob([content], {{ type: mimeType }});
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      URL.revokeObjectURL(link.href);
      link.remove();
    }}

    function csvCell(value) {{
      return `"${{String(value).replaceAll('"', '""')}}"`;
    }}

    document.getElementById('export-csv').addEventListener('click', () => {{
      const header = ['doc_id', 'page_index', 'page_type', 'has_music',
        'quality_comment'];
      const rows = changedRows().map(row => {{
        const state = states.get(rowKey(row));
        return [row.doc_id, row.page_index, state.page_type, state.has_music,
          state.quality_comment];
      }});
      const csv = [header, ...rows]
        .map(row => row.map(csvCell).join(','))
        .join('\\r\\n') + '\\r\\n';
      download('\\ufeff' + csv, 'thesis_label_corrections.csv',
        'text/csv;charset=utf-8');
    }});

    document.getElementById('export-json').addEventListener('click', () => {{
      const rows = changedRows().map(row => {{
        const state = states.get(rowKey(row));
        return {{
          doc_id: row.doc_id,
          page_index: row.page_index,
          page_type: state.page_type,
          has_music: Number(state.has_music),
          quality_comment: state.quality_comment,
          changed: true
        }};
      }});
      download(JSON.stringify(rows, null, 2), 'thesis_label_corrections.json',
        'application/json;charset=utf-8');
    }});

    render();
  </script>
</body>
</html>
"""


def write_editable_review_gallery(
    labels_path: Path,
    output_path: Path,
    *,
    project_root: Path = PROJECT_ROOT,
) -> int:
    """Read labels and write a static editable HTML gallery."""
    if not labels_path.is_file():
        raise FileNotFoundError(f"Labels CSV does not exist: {labels_path}")
    with labels_path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        columns = list(reader.fieldnames or [])
        missing = [column for column in REQUIRED_COLUMNS if column not in columns]
        if missing:
            raise ValueError(
                "Labels CSV is missing required columns: " + ", ".join(missing)
            )
        rows = list(reader)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        build_editable_review_gallery_html(
            rows,
            output_path,
            project_root=project_root,
        ),
        encoding="utf-8",
    )
    return len(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        count = write_editable_review_gallery(args.labels, args.out)
    except (FileNotFoundError, ValueError, OSError) as error:
        raise SystemExit(f"Error: {error}") from error
    print(f"Pages: {count}")
    print(f"Editable gallery: {args.out}")


if __name__ == "__main__":
    main()
