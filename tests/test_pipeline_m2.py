"""End-to-end M2 pipeline tests (stub source + mock LLM)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from crypto_trendwatching.adapters.sqlite_repository import SqliteRepository
from crypto_trendwatching.adapters.stubs import StubOnChain, StubSearch, StubWhale
from crypto_trendwatching.application.catalog import SourceRef
from crypto_trendwatching.application.pipeline import Pipeline
from crypto_trendwatching.domain.models import AgentTurn, Signal, Zone


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


class FakeLlm:
    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Any = None,
        max_tokens: int | None = None,
    ) -> str:
        del messages, tools, max_tokens
        return (
            '[{"name": "Тренд A", "definition": "Описание", "maturity": "растущий", '
            '"signal_indices": [0, 1]}]'
        )

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


def _pipeline(repo: SqliteRepository) -> Pipeline:
    return Pipeline(
        collector=FakeCollector(),
        repository=repo,
        embedder=OnesEmbedder(),
        llm=FakeLlm(),
        search=StubSearch(),
        onchain=StubOnChain(),
        whale=StubWhale(),
        catalog=_catalog(),
        liveness=lambda _url: True,
        unlock_fetcher=lambda _run_id: [],
    )


def test_pipeline_m2_catalog_and_report(tmp_path: Path) -> None:
    repo = SqliteRepository(tmp_path / "test.db")
    pipeline = _pipeline(repo)

    run = pipeline.run(_zone())

    assert run.status == "completed"
    assert run.report_md is not None
    assert "Тренд A" in run.report_md
    assert "[Ист](1)" in run.report_md
    assert "Source One" in run.report_md

    candidates = repo.list_trend_candidates(run.id or 0)
    assert len(candidates) == 1
    assert candidates[0].catalog_numbers == [1, 2]
    repo.close()


def test_pipeline_m2_anti_repeat_second_run(tmp_path: Path) -> None:
    repo = SqliteRepository(tmp_path / "test.db")
    pipeline = _pipeline(repo)

    first = pipeline.run(_zone())
    assert first.status == "completed"
    assert "ранее замечено" not in (first.report_md or "")

    second = pipeline.run(_zone())
    assert second.status == "completed"
    assert "ранее замечено" in (second.report_md or "")

    reported = repo.list_reported_trends()
    assert len(reported) == 1
    repo.close()
