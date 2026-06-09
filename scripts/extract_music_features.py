"""Extract music-theoretical features from MXL/MusicXML files."""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from notevision.music_features import (  # noqa: E402
    FEATURE_COLUMNS,
    extract_music_features,
    find_musicxml_files,
)


def extract_directory_features(
    mxl_dir: Path,
    *,
    recursive: bool = False,
) -> list[dict[str, object]]:
    """Extract every supported score under a directory."""
    return [
        extract_music_features(path)
        for path in find_musicxml_files(mxl_dir, recursive=recursive)
    ]


def extract_multiple_directories(
    directories: list[Path],
    *,
    recursive: bool = False,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[Path] = set()
    for directory in directories:
        for path in find_musicxml_files(directory, recursive=recursive):
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                rows.append(extract_music_features(path))
    return rows


def write_feature_csv(rows: list[dict[str, object]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FEATURE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(rows: list[dict[str, object]], summary_path: Path) -> None:
    statuses = Counter(str(row["extraction_status"]) for row in rows)
    sources = Counter(str(row["source"]) for row in rows)
    documents = {
        str(row["doc_id"]) for row in rows if row["doc_id"] != "unknown"
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        "\n".join(
            [
                "# Music features extraction summary",
                "",
                f"- Files processed: {len(rows)}",
                f"- Documents: {len(documents)}",
                f"- Success: {statuses['success']}",
                f"- Partial: {statuses['partial']}",
                f"- Failed: {statuses['failed']}",
                f"- Key source musicxml: {sources['musicxml']}",
                f"- Key source not_found: {sources['not_found']}",
                "",
                "`source=musicxml` means that the key signature was read "
                "directly from MusicXML. `source=not_found` means that the "
                "extractor did not infer or invent an absent value.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mxl-dir",
        type=Path,
        action="append",
        required=True,
        help="May be repeated for primary and fallback OMR directories.",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--recursive", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        rows = extract_multiple_directories(
            args.mxl_dir,
            recursive=args.recursive,
        )
        write_feature_csv(rows, args.out)
        write_summary(rows, args.summary)
    except (FileNotFoundError, OSError, ValueError) as error:
        raise SystemExit(f"Error: {error}") from error
    statuses = Counter(str(row["extraction_status"]) for row in rows)
    print(f"MusicXML files processed: {len(rows)}")
    print(f"Success: {statuses['success']}")
    print(f"Partial: {statuses['partial']}")
    print(f"Failed: {statuses['failed']}")
    print(f"CSV: {args.out}")
    print(f"Summary: {args.summary}")


if __name__ == "__main__":
    main()
