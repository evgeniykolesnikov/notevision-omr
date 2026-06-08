"""Import a flat external-expert package into the review database."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

from review_app.database import DEFAULT_DB_PATH, import_items

FILE_PATTERN = re.compile(
    r"^(?P<number>\d+)_(?P<doc_id>rsl\d+)_page_(?P<page>\d+)_"
    r"(?P<kind>scan|audio|track_(?P<track>\d+))\.(?P<extension>png|mp3)$",
    re.IGNORECASE,
)


def discover_package_items(package_dir: Path) -> list[dict[str, object]]:
    if not package_dir.is_dir():
        raise FileNotFoundError(f"Expert package does not exist: {package_dir}")

    grouped: dict[int, dict[str, object]] = {}
    for path in sorted(package_dir.iterdir()):
        if not path.is_file():
            continue
        match = FILE_PATTERN.match(path.name)
        if not match:
            continue
        item_number = int(match.group("number"))
        item = grouped.setdefault(
            item_number,
            {
                "item_number": item_number,
                "doc_id": match.group("doc_id"),
                "page_index": int(match.group("page")),
                "scan_path": "",
                "audio_path": "",
                "track_paths": [],
            },
        )
        if (
            item["doc_id"] != match.group("doc_id")
            or item["page_index"] != int(match.group("page"))
        ):
            raise ValueError(
                f"Conflicting files for item {item_number}: {path.name}"
            )
        kind = match.group("kind").lower()
        if kind == "scan":
            item["scan_path"] = path.name
        elif kind == "audio":
            item["audio_path"] = path.name
        else:
            item["track_paths"].append(path.name)  # type: ignore[union-attr]

    if not grouped:
        raise ValueError(f"No review items found in package: {package_dir}")

    items = []
    for item_number in sorted(grouped):
        item = grouped[item_number]
        missing = [
            name
            for name in ("scan_path", "audio_path")
            if not item[name]
        ]
        if missing:
            raise ValueError(
                f"Item {item_number} is missing: {', '.join(missing)}"
            )
        item["track_paths"] = sorted(
            item["track_paths"],
            key=lambda value: int(
                re.search(r"_track_(\d+)\.mp3$", value).group(1)  # type: ignore[union-attr]
            ),
        )
        items.append(item)
    return items


def import_package(
    package_dir: Path,
    db_path: Path = DEFAULT_DB_PATH,
) -> int:
    items = discover_package_items(package_dir.resolve())
    return import_items(db_path, items)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(os.getenv("REVIEW_APP_DB", DEFAULT_DB_PATH)),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        count = import_package(args.package_dir, args.db)
    except (FileNotFoundError, ValueError, OSError) as error:
        raise SystemExit(f"Error: {error}") from error
    print(f"Imported review items: {count}")
    print(f"Database: {args.db}")


if __name__ == "__main__":
    main()
