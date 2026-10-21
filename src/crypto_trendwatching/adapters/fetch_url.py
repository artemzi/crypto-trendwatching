"""fetch_url-коллектор: httpx забирает страницу, LLM извлекает элементы."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from crypto_trendwatching.application.parsing import parse_json_list
from crypto_trendwatching.domain.models import Signal, Source, Zone
from crypto_trendwatching.domain.ports import LLMClient

logger = logging.getLogger(__name__)

_MAX_HTML_CHARS = 50_000


class FetchUrlCollector:
    """Собирает сигналы с источников `method: fetch_url` через LLM-экстракт."""

    def __init__(
        self, sources: list[Source], llm: LLMClient, timeout: float = 20.0
    ) -> None:
        self._sources = [s for s in sources if s.method == "fetch_url"]
        self._llm = llm
        self._timeout = timeout

    def collect(self, zone: Zone) -> list[Signal]:
        signals: list[Signal] = []
        for source in self._sources:
            signals.extend(self._collect_source(source, zone))
        return signals

    def _collect_source(self, source: Source, zone: Zone) -> list[Signal]:
        try:
            text = self._fetch(source.url)
            if not text:
                return []
            items = self._extract(source, text)
        except Exception:
            logger.exception("не удалось обработать %s", source.url)
            return []
        return [
            Signal(
                url=item.get("url") or source.url,
                source_id=source.id,
                zone_id=zone.id,
                title=item.get("title"),
                summary=item.get("summary"),
                published_at=item.get("published_at"),
            )
            for item in items
        ]

    def _fetch(self, url: str) -> str:
        with httpx.Client(timeout=self._timeout, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.text[:_MAX_HTML_CHARS]

    def _extract(self, source: Source, text: str) -> list[dict[str, Any]]:
        messages = [
            {
                "role": "system",
                "content": (
                    "Ты извлекаешь свежие материалы из HTML-страницы источника. "
                    "Верни только JSON-массив объектов с полями: "
                    "title (str), summary (str), url (str), published_at (ISO8601 или null). "
                    "Без пояснений и markdown — только валидный JSON."
                ),
            },
            {
                "role": "user",
                "content": f"Источник: {source.name} ({source.url})\n\nHTML:\n{text}",
            },
        ]
        raw = self._llm.complete(messages, max_tokens=2000)
        return parse_json_list(raw)
