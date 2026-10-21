"""Tests for the investment interpretation block (D-04)."""

from __future__ import annotations

import json
from typing import Any

from crypto_trendwatching.application.interpret import DISCLAIMER, interpret_candidate
from crypto_trendwatching.domain.models import AgentTurn, TrendCandidate


class _InterpretLlm:
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


def _candidate() -> TrendCandidate:
    return TrendCandidate(run_id=1, name="Тренд", definition="Описание")


def test_interpretation_parses_fields_and_adds_disclaimer() -> None:
    llm = _InterpretLlm(
        json.dumps(
            {
                "direction": "бычий",
                "horizon": "месяцы",
                "catalysts": ["разлок", "апгрейд"],
                "risk_flags": ["регуляторный риск"],
                "onchain_status": "подтверждено",
            }
        )
    )

    result = interpret_candidate(llm, _candidate(), "TVL: рост", "подтверждение")

    assert result.direction == "бычий"
    assert result.horizon == "месяцы"
    assert result.catalysts == ["разлок", "апгрейд"]
    assert result.risk_flags == ["регуляторный риск"]
    assert result.onchain_status == "подтверждено"
    assert result.disclaimer == DISCLAIMER


def test_interpretation_fail_open_keeps_disclaimer() -> None:
    llm = _InterpretLlm("not json")

    result = interpret_candidate(llm, _candidate(), "нет данных", None)

    assert result.direction is None
    assert result.catalysts == []
    assert result.disclaimer == DISCLAIMER
