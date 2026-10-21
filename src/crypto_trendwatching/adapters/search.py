"""Яндекс Search API v2 (RU-поиск) за портом SearchProvider."""

from __future__ import annotations

import logging

import httpx

from crypto_trendwatching.domain.models import SearchResult

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://yandex.com/api/search/v2/query"


class YandexSearchProvider:
    """RU-поиск через Яндекс Search API v2; fail-open — при ошибке возвращает [].

    Примечание: точный эндпоинт/схема ответа зависят от актуальной версии API —
    при первом реальном прогоне проверить по документации Яндекса.
    """

    def __init__(
        self,
        api_key: str,
        folder_id: str,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = 20.0,
    ) -> None:
        self._api_key = api_key
        self._folder_id = folder_id
        self._base_url = base_url
        self._timeout = timeout

    def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    self._base_url,
                    headers={
                        "Authorization": f"Api-Key {self._api_key}",
                        "x-folder-id": self._folder_id,
                    },
                    json={"query": query, "count": limit},
                )
                response.raise_for_status()
                data = response.json()
        except Exception:
            logger.exception("поиск Яндекса не удался: %r", query)
            return []
        results = data.get("results", []) if isinstance(data, dict) else []
        return [
            SearchResult(
                provider="yandex",
                url=item.get("url", ""),
                title=item.get("title"),
                snippet=item.get("text"),
            )
            for item in results
            if isinstance(item, dict)
        ]
