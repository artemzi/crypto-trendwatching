"""Композитные коллекторы: поиск → сигналы и объединение нескольких коллекторов."""

from __future__ import annotations

from crypto_trendwatching.domain.models import Signal, Zone
from crypto_trendwatching.domain.ports import SearchProvider, SourceCollector


class SearchCollector:
    """Превращает результаты поискового провайдера в сигналы для зоны."""

    def __init__(self, provider: SearchProvider, max_queries: int = 3) -> None:
        self._provider = provider
        self._max_queries = max_queries

    def collect(self, zone: Zone) -> list[Signal]:
        signals: list[Signal] = []
        for keyword in zone.seed_keywords[: self._max_queries]:
            for result in self._provider.search(keyword):
                signals.append(
                    Signal(
                        url=result.url,
                        source_id=result.provider,
                        zone_id=zone.id,
                        title=result.title,
                        summary=result.snippet,
                    )
                )
        return signals


class CompositeCollector:
    """Объединяет несколько SourceCollector в один."""

    def __init__(self, collectors: list[SourceCollector]) -> None:
        self._collectors = collectors

    def collect(self, zone: Zone) -> list[Signal]:
        result: list[Signal] = []
        for collector in self._collectors:
            result.extend(collector.collect(zone))
        return result
