"""Tests for the Yandex search provider and search collector."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from crypto_trendwatching.adapters.collectors import SearchCollector
from crypto_trendwatching.adapters.search import YandexSearchProvider
from crypto_trendwatching.domain.models import SearchResult, Zone


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {"results": [{"url": "https://x.com/1", "title": "T", "text": "S"}]}


class FakeClient:
    def __init__(self, **kwargs: object) -> None:
        del kwargs

    def __enter__(self) -> FakeClient:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        del url, kwargs
        return FakeResponse()


class RaisingClient:
    def __init__(self, **kwargs: object) -> None:
        del kwargs

    def __enter__(self) -> RaisingClient:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        del url, kwargs
        raise httpx.HTTPError("boom")


class StubSearchProvider:
    def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        del limit
        return [
            SearchResult(
                provider="stub", url="https://x.com/1", title=query, snippet="s"
            )
        ]


def test_yandex_search_returns_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "Client", FakeClient)
    provider = YandexSearchProvider("key", "folder")
    results = provider.search("test")
    assert len(results) == 1
    assert results[0].url == "https://x.com/1"
    assert results[0].provider == "yandex"


def test_yandex_search_fail_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "Client", RaisingClient)
    provider = YandexSearchProvider("key", "folder")
    assert provider.search("test") == []


def test_search_collector_converts_to_signals() -> None:
    collector = SearchCollector(StubSearchProvider(), max_queries=2)
    zone = Zone(id="z", name="Z", seed_keywords=["kw1", "kw2", "kw3"])
    signals = collector.collect(zone)
    assert len(signals) == 2
    assert signals[0].zone_id == "z"
    assert signals[0].source_id == "stub"
