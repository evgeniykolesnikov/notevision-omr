"""Tests for thesis dataset statistics and Markdown reporting."""

import csv
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_dataset_statistics import (
    PAGE_TYPES,
    STATISTICS_COLUMNS,
    build_dataset_markdown,
    build_dataset_statistics,
    write_dataset_statistics,
)


class DatasetStatisticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [
            {
                "doc_id": f"doc-{index % 2}",
                "page_type": page_type,
                "has_music": "1" if page_type in {"music", "mixed"} else "0",
                "has_music_pred": "1" if page_type == "music" else "0",
            }
            for index, page_type in enumerate(PAGE_TYPES)
        ]

    def test_counts_total_and_each_page_type(self) -> None:
        statistics = build_dataset_statistics(self.rows)

        self.assertEqual(statistics["total_pages"], len(PAGE_TYPES))
        for page_type in PAGE_TYPES:
            self.assertEqual(statistics[page_type], 1)

    def test_markdown_uses_actual_values_and_required_sections(self) -> None:
        statistics = build_dataset_statistics(self.rows)
        report = build_dataset_markdown(
            statistics,
            self.rows,
            Path("data/labels/test.csv"),
        )

        self.assertIn("## Размер корпуса", report)
        self.assertIn("## Распределение классов", report)
        self.assertIn("## Источники данных", report)
        self.assertIn("## Типичные ошибки detector", report)
        self.assertIn("## Ограничения корпуса", report)
        self.assertIn(f"**{len(PAGE_TYPES)} страниц**", report)
        self.assertIn("| `music` | 1 |", report)

    def test_output_csv_has_expected_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            labels_path = root / "labels.csv"
            output_path = root / "statistics.csv"
            with labels_path.open("w", encoding="utf-8", newline="") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=list(self.rows[0]))
                writer.writeheader()
                writer.writerows(self.rows)

            write_dataset_statistics(labels_path, output_path)
            with output_path.open(encoding="utf-8", newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                list(reader)

            self.assertEqual(reader.fieldnames, STATISTICS_COLUMNS)


if __name__ == "__main__":
    unittest.main()
