"""Tests for the M1 pipeline and the RSS collector."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import feedparser
import numpy as np
import numpy.typing as npt
import pytest

from crypto_trendwatching.adapters.rss_collector import RssCollector
from crypto_trendwatching.adapters.sqlite_repository import SqliteRepository
from crypto_trendwatching.adapters.stubs import StubOnChain, StubSearch, StubWhale
from crypto_trendwatching.application.pipeline import Pipeline
from crypto_trendwatching.domain.models import AgentTurn, Signal, Source, Zone


class OnesEmbedder:
    def embed(self, texts: list[str]) -> npt.NDArray[np.float16]:
        return np.ones((len(texts), 1024), dtype=np.float16)


class FakeCollector:
    def collect(self, zone: Zone) -> list[Signal]:
        return [
            Signal(
                url="https://example.com/1",
                source_id="s1",
                zone_id=zone.id,
                title="A",
                summary="B",
            ),
            Signal(
                url="https://example.com/2",
                source_id="s2",
                zone_id=zone.id,
                title="C",
                summary="D",
            ),
        ]


class FakeLlm:
    def __init__(self, response: str) -> None:
        self._response = response

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Any = None,
        max_tokens: int | None = None,
    ) -> str:
        del messages, tools, max_tokens
        return self._response

    def complete_with_tools(
        self, messages: list[dict[str, Any]], tools: Any = None
    ) -> AgentTurn:
        del messages, tools
        return AgentTurn(content="")


def _make_zone() -> Zone:
    return Zone(id="infrastructure", name="Инфраструктура", enabled=True)


def test_pipeline_m1(tmp_path: Path) -> None:
    repo = SqliteRepository(tmp_path / "test.db")
    pipeline = Pipeline(
        collector=FakeCollector(),
        repository=repo,
        embedder=OnesEmbedder(),
        llm=FakeLlm(
            '[{"name": "Тренд A", "definition": "Описание", "maturity": "растущий", '
            '"signal_indices": [0, 1]}]'
        ),
        search=StubSearch(),
        onchain=StubOnChain(),
        whale=StubWhale(),
    )

    run = pipeline.run(_make_zone())

    assert run.status == "completed"
    assert run.report_md is not None
    assert "Тренд A" in run.report_md

    assert len(repo.list_signals("infrastructure")) == 2
    candidates = repo.list_trend_candidates(run.id or 0)
    assert len(candidates) == 1
    assert candidates[0].name == "Тренд A"
    repo.close()


def test_rss_collector_parses_feed(monkeypatch: pytest.MonkeyPatch) -> None:
    entries = [
        {
            "link": "https://example.com/1",
            "title": "One",
            "summary": "Summary one",
            "published_parsed": None,
        },
        {"link": "https://example.com/2", "title": "Two"},
    ]
    monkeypatch.setattr(feedparser, "parse", lambda _: SimpleNamespace(entries=entries))

    sources = [
        Source(
            id="s",
            name="S",
            url="https://example.com/",
            feed_url="https://example.com/feed",
            region="EN",
            method="rss",
            availability_from_rf="да",
        )
    ]
    collector = RssCollector(sources)
    signals = collector.collect(_make_zone())

    assert len(signals) == len(entries)
    assert signals[0].zone_id == "infrastructure"
    assert signals[0].source_id == "s"
    assert signals[0].title == "One"
