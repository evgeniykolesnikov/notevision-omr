"""Tests for review application password verification."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from review_app.auth import verify_password
from review_app.config import DEFAULT_LOCAL_PASSWORD, load_review_app_password


class ReviewAuthTests(unittest.TestCase):
    def test_ascii_password(self) -> None:
        self.assertTrue(verify_password("secret-123", "secret-123"))

    def test_cyrillic_password(self) -> None:
        self.assertTrue(verify_password("Музыка-2026", "Музыка-2026"))

    def test_wrong_password(self) -> None:
        self.assertFalse(verify_password("wrong", "Музыка-2026"))

    def test_empty_expected_password_is_rejected(self) -> None:
        self.assertFalse(verify_password("", ""))
        self.assertFalse(verify_password("anything", ""))

    def test_password_prefers_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            (root / ".env").write_text(
                "REVIEW_APP_PASSWORD=file-secret\n",
                encoding="utf-8",
            )
            with patch.dict(
                "os.environ",
                {"REVIEW_APP_PASSWORD": "env-secret"},
                clear=False,
            ):
                password, source = load_review_app_password(root)
        self.assertEqual(password, "env-secret")
        self.assertEqual(source, "environment")

    def test_password_reads_dotenv_when_environment_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            (root / ".env").write_text(
                "# local config\nREVIEW_APP_PASSWORD=file-secret\n",
                encoding="utf-8",
            )
            with patch.dict("os.environ", {}, clear=True):
                password, source = load_review_app_password(root)
        self.assertEqual(password, "file-secret")
        self.assertEqual(source, "env_file")

    def test_password_uses_local_default_for_development(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            with patch.dict("os.environ", {}, clear=True):
                password, source = load_review_app_password(Path(temporary_dir))
        self.assertEqual(password, DEFAULT_LOCAL_PASSWORD)
        self.assertEqual(source, "default")


if __name__ == "__main__":
    unittest.main()
