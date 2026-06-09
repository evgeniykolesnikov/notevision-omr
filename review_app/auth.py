"""Authentication helpers for master-password and reviewer-token sessions."""

from __future__ import annotations

import hashlib
import hmac

COOKIE_NAME = "notevision_review_auth"
REVIEWER_COOKIE_NAME = "notevision_reviewer_id"
TOKEN_MESSAGE = b"notevision-omr-expert-review"


def build_auth_token(password: str) -> str:
    return hmac.new(
        password.encode("utf-8"),
        TOKEN_MESSAGE,
        hashlib.sha256,
    ).hexdigest()


def verify_password(candidate: str, expected: str) -> bool:
    return bool(expected) and hmac.compare_digest(
        candidate.encode("utf-8"),
        expected.encode("utf-8"),
    )


def verify_auth_token(token: str | None, password: str) -> bool:
    if not token or not password:
        return False
    return hmac.compare_digest(token, build_auth_token(password))


def build_reviewer_session(reviewer_id: int, password: str) -> str:
    payload = str(reviewer_id)
    signature = hmac.new(
        password.encode("utf-8"),
        f"reviewer-id:{payload}".encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}.{signature}"


def read_reviewer_session(token: str | None, password: str) -> int | None:
    if not token or not password or "." not in token:
        return None
    payload, signature = token.rsplit(".", 1)
    expected = hmac.new(
        password.encode("utf-8"),
        f"reviewer-id:{payload}".encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        reviewer_id = int(payload)
    except ValueError:
        return None
    return reviewer_id if reviewer_id > 0 else None
