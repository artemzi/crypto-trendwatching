"""End-to-end M3 pipeline test (stub sources + mock LLM) covering all 8 sections."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from crypto_trendwatching.adapters.sqlite_repository import SqliteRepository
from crypto_trendwatching.adapters.stubs import StubSearch
from crypto_trendwatching.application.catalog import SourceRef
from crypto_trendwatching.application.pipeline import Pipeline
from crypto_trendwatching.domain.models import (
    AgentTurn,
    Signal,
    WhaleTransfer,
    Zone,
)


class OnesEmbedder:
    def embed(self, texts: list[str]) -> npt.NDArray[np.float16]:
        return np.ones((len(texts), 1024), dtype=np.float16)


class FakeCollector:
    def collect(self, zone: Zone) -> list[Signal]:
        return [
            Signal(
                url="https://example.com/1", source_id="s1", zone_id=zone.id, title="A"
            ),
            Signal(
                url="https://example.com/2", source_id="s2", zone_id=zone.id, title="B"
            ),
        ]


class FakeWhale:
    def transfers(
        self, *, min_usd: float, since: str | None = None
    ) -> list[WhaleTransfer]:
        del min_usd, since
        return [
            WhaleTransfer(
                amount_usd=2_000_000.0,
                asset="ETH",
                from_address="0x1",
                to_address="0x2",
                timestamp="2026-10-20T00:00:00+00:00",
            )
        ]


class FakeOnChain:
    def tvl(self, _protocol: str) -> float:
        return 200.0

    def volume(self, _protocol: str, _window: str) -> float:
        return 0.0

    def price(self, _coin: str) -> float:
        return 100.0

    def change(self, _metric: str, _subject: str, _window_days: int) -> float | None:
        return 5.0


class DispatchLlm:
    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Any = None,
        max_tokens: int | None = None,
    ) -> str:
        del tools, max_tokens
        system = next((m["content"] for m in messages if m.get("role") == "system"), "")
        if "Сгруппируй" in system:
            return (
                '[{"name": "Тренд A", "definition": "Описание", "maturity": "растущий", '
                '"signal_indices": [0, 1]}]'
            )
        if "инвестиционную интерпретацию" in system:
            return (
                '{"direction": "бычий", "horizon": "месяцы", '
                '"catalysts": ["разлок"], "risk_flags": ["регуляторный риск"], '
                '"onchain_status": "подтверждено"}'
            )
        if "whale-активность" in system:
            return '{"verdict": "подтверждение", "reason": "киты накапливают"}'
        if "события-катализаторы" in system:
            return '[{"title": "Апгрейд сети", "event_date": "2026-11-01", "category": "upgrade"}]'
        return '{"verdict": "sound", "reason": "ok"}'

    def complete_with_tools(
        self, messages: list[dict[str, Any]], tools: Any = None
    ) -> AgentTurn:
        del messages, tools
        return AgentTurn(content="")


def _catalog() -> dict[str, SourceRef]:
    return {
        "s1": SourceRef(1, "s1", "Source One", "https://s1.example.com/"),
        "s2": SourceRef(2, "s2", "Source Two", "https://s2.example.com/"),
    }


def _zone() -> Zone:
    return Zone(id="infrastructure", name="Инфраструктура", enabled=True)


def test_pipeline_m3_full_digest(tmp_path: Path) -> None:
    repo = SqliteRepository(tmp_path / "test.db")
    pipeline = Pipeline(
        collector=FakeCollector(),
        repository=repo,
        embedder=OnesEmbedder(),
        llm=DispatchLlm(),
        search=StubSearch(),
        onchain=FakeOnChain(),
        whale=FakeWhale(),
        catalog=_catalog(),
        liveness=lambda _url: True,
        unlock_fetcher=lambda _run_id: [],
    )

    run = pipeline.run(_zone())

    assert run.status == "completed"
    report = run.report_md or ""
    for section in (
        "## Резюме недели",
        "## Тренды",
        "## Развитие ранее замеченных трендов",
        "## Слабые сигналы",
        "## Whale-активность недели",
        "## Катализаторы следующей недели",
        "## Источники",
        "## Воронка",
    ):
        assert section in report

    assert "Тренд A" in report
    assert "бычий" in report
    assert "Whale-активность: подтверждение" in report
    assert "Апгрейд сети" in report
    assert "Не является индивидуальной инвестиционной рекомендацией." in report
    assert run.report_docx is not None and run.report_docx[:2] == b"PK"

    assert len(repo.list_whale_transfers(run.id or 0)) == 1
    assert len(repo.list_catalysts(run.id or 0)) == 1
    repo.close()
