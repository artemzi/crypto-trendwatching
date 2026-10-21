"""Tests for the agentic loop (tool dispatch, evidence accumulation, final notes)."""

from __future__ import annotations

from typing import Any

from crypto_trendwatching.agent.loop import AgentLoop
from crypto_trendwatching.agent.tools import AgentTools, _html_to_text
from crypto_trendwatching.domain.models import (
    AgentTurn,
    SearchResult,
    Signal,
    ToolCall,
    TrendCandidate,
)


def test_html_to_text_strips_markup() -> None:
    raw = (
        "<html><head><style>body{color:red}</style></head><body>"
        "<p>Hello <b>World</b> &amp; crypto</p>"
        "<script>var x = 1;</script></body></html>"
    )
    text = _html_to_text(raw)
    assert "Hello World & crypto" in text
    assert "<" not in text
    assert "body{color:red}" not in text


class FakeSearch:
    def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        del limit
        return [
            SearchResult(provider="fake", url="https://x.example.com/a", snippet=query)
        ]


class FakeOnChain:
    def tvl(self, _protocol: str) -> float:
        return 1_000.0

    def volume(self, _protocol: str, window: str) -> float:
        del window
        return 2_000.0

    def price(self, coin: str) -> float:
        del coin
        return 50.0

    def change(self, metric: str, subject: str, window_days: int) -> float | None:
        del metric, subject
        return 10.0 if window_days == 7 else None


class ScriptedLlm:
    def __init__(self, turns: list[AgentTurn]) -> None:
        self._turns = list(turns)
        self._cursor = 0

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Any = None,
        max_tokens: int | None = None,
    ) -> str:
        del messages, tools, max_tokens
        return "финальные заметки"

    def complete_with_tools(
        self, messages: list[dict[str, Any]], tools: Any = None
    ) -> AgentTurn:
        del messages, tools
        turn = self._turns[self._cursor]
        self._cursor += 1
        return turn


def _candidate() -> TrendCandidate:
    return TrendCandidate(run_id=1, name="Тренд", id=7)


def _signals() -> list[Signal]:
    return [Signal(url="https://s.example.com/1", title="S1", source_id="s")]


def test_loop_executes_tools_and_collects_evidence() -> None:
    turns = [
        AgentTurn(
            tool_calls=[
                ToolCall(id="c1", name="search_web", arguments={"query": "defi"}),
                ToolCall(
                    id="c2",
                    name="check_onchain",
                    arguments={"metric": "tvl", "subject": "aave"},
                ),
            ]
        ),
        AgentTurn(content="Заметки: тренд подтверждён"),
    ]
    loop = AgentLoop(ScriptedLlm(turns), AgentTools(FakeSearch(), FakeOnChain()))

    result = loop.research(_candidate(), _signals(), run_id=1)

    assert result.notes == "Заметки: тренд подтверждён"
    assert len(result.evidence) == 1
    assert result.evidence[0].candidate_id == 7
    assert len(result.onchain) == 1
    assert result.onchain[0].run_id == 1
    assert result.onchain[0].candidate_id == 7
    assert result.onchain[0].metric == "tvl"


def test_loop_forces_final_after_rounds() -> None:
    turns = [
        AgentTurn(
            tool_calls=[ToolCall(id="c1", name="search_web", arguments={"query": "x"})]
        )
        for _ in range(5)
    ]
    loop = AgentLoop(
        ScriptedLlm(turns), AgentTools(FakeSearch(), FakeOnChain()), max_rounds=2
    )

    result = loop.research(_candidate(), _signals(), run_id=1)

    assert result.notes == "финальные заметки"


def test_loop_dedups_evidence_by_url() -> None:
    turns = [
        AgentTurn(
            tool_calls=[
                ToolCall(id="c1", name="search_web", arguments={"query": "a"}),
                ToolCall(id="c2", name="search_web", arguments={"query": "b"}),
            ]
        ),
        AgentTurn(content="готово"),
    ]
    loop = AgentLoop(ScriptedLlm(turns), AgentTools(FakeSearch(), FakeOnChain()))

    result = loop.research(_candidate(), _signals(), run_id=1)

    assert len(result.evidence) == 1
