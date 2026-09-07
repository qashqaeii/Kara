"""
Persist and load Kara session cookies between restarts.
"""

from __future__ import annotations

import logging
from pathlib import Path

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def serialize_session_cookies(session: requests.Session) -> str:
    parts = []
    for cookie in session.cookies:
        parts.append(f"{cookie.name}={cookie.value}")
    return "; ".join(parts)


def cookie_file_path() -> Path:
    return Path(settings.KARA_COOKIE_FILE)


def save_session_cookies(session: requests.Session) -> None:
    if not getattr(settings, "KARA_PERSIST_COOKIES", True):
        return

    cookie_str = serialize_session_cookies(session)
    if not cookie_str:
        return

    path = cookie_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cookie_str, encoding="utf-8")
    logger.info("Kara session cookies persisted to %s", path)


def load_persisted_cookies() -> str | None:
    path = cookie_file_path()
    if not path.exists():
        return None
    cookie = path.read_text(encoding="utf-8").strip()
    return cookie or None


def apply_cookie_string(session: requests.Session, cookie: str) -> None:
    """Parse ``name=value; ...`` into the session cookie jar (not a raw Cookie header)."""
    from urllib.parse import urlparse

    from django.conf import settings

    base = getattr(settings, "KARA_BASE_URL", "http://app.pakhshmarket.com")
    host = urlparse(base).hostname or "app.pakhshmarket.com"

    for part in cookie.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        name, value = name.strip(), value.strip()
        if not name:
            continue
        session.cookies.set(name, value, domain=host, path="/")
