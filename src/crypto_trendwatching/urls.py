"""Чистые утилиты нормализации URL (без зависимостей от application/agent)."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

_TRACKING_PREFIXES = ("utm_", "fbclid", "gclid", "yclid", "_ga", "_gl")


def normalize_url(url: str) -> str:
    """Каноническая форма URL для дедупликации."""
    parts = urlsplit(url.strip())
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parts.path.rstrip("/") or "/"
    query = _strip_tracking(parts.query)
    return urlunsplit((parts.scheme.lower(), netloc, path, query, ""))


def _strip_tracking(query: str) -> str:
    if not query:
        return ""
    kept = [
        param
        for param in query.split("&")
        if not param.split("=", 1)[0].lower().startswith(_TRACKING_PREFIXES)
    ]
    return "&".join(kept)
