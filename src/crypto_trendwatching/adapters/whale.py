"""Whale-адаптер: Whale Alert (free tier) за портом WhaleClient."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from crypto_trendwatching.domain.models import WhaleTransfer

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.whale-alert.io/v1"


class WhaleAlertClient:
    """Сбор крупных трансферов (≥ min_usd) через Whale Alert API; fail-open."""

    def __init__(
        self,
        api_key: str,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = 20.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def transfers(
        self, *, min_usd: float, since: str | None = None
    ) -> list[WhaleTransfer]:
        params: dict[str, Any] = {
            "api_key": self._api_key,
            "min_value": int(min_usd),
            "limit": 100,
        }
        if since is not None:
            unix = _to_unix(since)
            if unix is not None:
                params["start"] = unix
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(f"{self._base_url}/transactions", params=params)
                response.raise_for_status()
                data = response.json()
        except Exception:
            logger.exception("Whale Alert запрос не удался")
            return []
        transactions = data.get("transactions", []) if isinstance(data, dict) else []
        return [
            self._to_transfer(item) for item in transactions if isinstance(item, dict)
        ]

    def _to_transfer(self, item: dict[str, Any]) -> WhaleTransfer:
        return WhaleTransfer(
            amount_usd=_as_float(item.get("amount_usd")),
            asset=item.get("symbol") or item.get("asset"),
            from_address=_address(item.get("from")),
            to_address=_address(item.get("to")),
            timestamp=_to_iso(item.get("timestamp")),
        )


def _address(entity: Any) -> str | None:
    if isinstance(entity, dict):
        value = entity.get("address")
        return value if isinstance(value, str) else None
    return None


def _as_float(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _to_unix(since: str) -> int | None:
    try:
        return int(datetime.fromisoformat(since).timestamp())
    except (ValueError, TypeError):
        return None


def _to_iso(timestamp: Any) -> str | None:
    if isinstance(timestamp, (int, float)):
        return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()
    if isinstance(timestamp, str):
        return timestamp
    return None
