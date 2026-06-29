"""Configuration helpers for the protected review application."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_LOCAL_PASSWORD = "notevision"


def load_review_app_password(
    project_root: Path,
    explicit_password: str | None = None,
) -> tuple[str, str]:
    """Resolve the review app password from explicit args, env, .env, or local default."""
    if explicit_password is not None:
        return explicit_password, "explicit"
    env_password = os.getenv("REVIEW_APP_PASSWORD", "").strip()
    if env_password:
        return env_password, "environment"
    env_file = project_root / ".env"
    if env_file.is_file():
        for raw_line in env_file.read_text(
            encoding="utf-8-sig", errors="replace"
        ).splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() != "REVIEW_APP_PASSWORD":
                continue
            file_password = value.strip().strip('"').strip("'")
            if file_password:
                return file_password, "env_file"
    return DEFAULT_LOCAL_PASSWORD, "default"
