"""RSS-коллектор (feedparser)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import feedparser

from crypto_trendwatching.domain.models import Signal, Source, Zone

logger = logging.getLogger(__name__)


class RssCollector:
    """Собирает фиды всех включённых rss-источников, помечая их zone_id прогона."""

    def __init__(self, sources: list[Source]) -> None:
        self._sources = [s for s in sources if s.method == "rss" and s.feed_url]

    def collect(self, zone: Zone) -> list[Signal]:
        signals: list[Signal] = []
        for source in self._sources:
            signals.extend(self._collect_source(source, zone))
        return signals

    def _collect_source(self, source: Source, zone: Zone) -> list[Signal]:
        feed_url = source.feed_url
        if feed_url is None:
            return []
        try:
            parsed = feedparser.parse(feed_url)
        except Exception:
            logger.exception("не удалось получить фид %s", feed_url)
            return []
        return [self._to_signal(source, zone, entry) for entry in parsed.entries]

    def _to_signal(self, source: Source, zone: Zone, entry: Any) -> Signal:
        return Signal(
            url=entry.get("link", ""),
            source_id=source.id,
            zone_id=zone.id,
            title=entry.get("title"),
            summary=entry.get("summary"),
            published_at=_to_iso(entry.get("published_parsed")),
        )


def _to_iso(parsed: Any) -> str | None:
    if not parsed:
        return None
    try:
        return datetime(
            parsed[0],
            parsed[1],
            parsed[2],
            parsed[3],
            parsed[4],
            parsed[5],
            tzinfo=UTC,
        ).isoformat()
    except (TypeError, ValueError, IndexError):
        return None
