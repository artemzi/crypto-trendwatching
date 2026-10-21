"""Tests for the catalyst calendar (FR-9)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from crypto_trendwatching.application.catalysts import (
    extract_catalysts,
    fetch_unlock_catalysts,
)
from crypto_trendwatching.domain.models import AgentTurn, Signal, Zone


class _CatalystLlm:
    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Any = None,
        max_tokens: int | None = None,
    ) -> str:
        del messages, tools, max_tokens
        return (
            '[{"title": "Апгрейд сети", "event_date": "2026-11-01", '
            '"category": "upgrade"}]'
        )

    def complete_with_tools(
        self, messages: list[dict[str, Any]], tools: Any = None
    ) -> AgentTurn:
        del messages, tools
        return AgentTurn(content="")


def _zone() -> Zone:
    return Zone(id="infrastructure", name="Инфраструктура", enabled=True)


def _signals() -> list[Signal]:
    return [
        Signal(
            url="https://x.example.com/1", title="новость", published_at="2026-10-21"
        )
    ]


def test_extract_catalysts_parses_items() -> None:
    catalysts = extract_catalysts(_CatalystLlm(), _zone(), _signals(), run_id=1)
    assert len(catalysts) == 1
    assert catalysts[0].title == "Апгрейд сети"
    assert catalysts[0].category == "upgrade"
    assert catalysts[0].event_date == "2026-11-01"


def test_extract_catalysts_empty_signals() -> None:
    assert extract_catalysts(_CatalystLlm(), _zone(), [], run_id=1) == []


def test_fetch_unlock_catalysts_fail_open(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Failing:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            return None

        def __enter__(self) -> _Failing:
            return self

        def __exit__(self, *_a: Any) -> None:
            return None

        def get(self, _url: str) -> None:
            raise RuntimeError("network down")

    monkeypatch.setattr(httpx, "Client", _Failing)
    assert fetch_unlock_catalysts(1) == []
