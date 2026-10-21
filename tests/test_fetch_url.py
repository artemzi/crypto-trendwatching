"""Tests for the fetch_url collector."""

from __future__ import annotations

from typing import Any

import pytest

from crypto_trendwatching.adapters.fetch_url import FetchUrlCollector
from crypto_trendwatching.domain.models import AgentTurn, Source, Zone


class FakeLlm:
    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Any = None,
        max_tokens: int | None = None,
    ) -> str:
        del messages, tools, max_tokens
        return '[{"title": "A", "summary": "S", "url": "https://x.com/1"}]'

    def complete_with_tools(
        self, messages: list[dict[str, Any]], tools: Any = None
    ) -> AgentTurn:
        del messages, tools
        return AgentTurn(content="")


def _make_source() -> Source:
    return Source(
        id="s",
        name="S",
        url="https://example.com/",
        region="EN",
        method="fetch_url",
        availability_from_rf="да",
    )


def _make_zone() -> Zone:
    return Zone(id="z", name="Z", enabled=True)


def test_collect_extracts_items(monkeypatch: pytest.MonkeyPatch) -> None:
    collector = FetchUrlCollector([_make_source()], FakeLlm())
    monkeypatch.setattr(collector, "_fetch", lambda _: "<html>page</html>")

    signals = collector.collect(_make_zone())

    assert len(signals) == 1
    assert signals[0].title == "A"
    assert signals[0].url == "https://x.com/1"
    assert signals[0].zone_id == "z"


def test_collect_fail_open(monkeypatch: pytest.MonkeyPatch) -> None:
    collector = FetchUrlCollector([_make_source()], FakeLlm())

    def raise_error(_url: str) -> str:
        raise RuntimeError("network down")

    monkeypatch.setattr(collector, "_fetch", raise_error)

    assert collector.collect(_make_zone()) == []
