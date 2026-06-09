"""Tests for review application password verification."""

import unittest

from review_app.auth import verify_password


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


if __name__ == "__main__":
    unittest.main()
