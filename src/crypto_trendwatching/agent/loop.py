"""Оркестратор agentic loop: LLM вызывает инструменты до N раундов, затем итог."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, replace
from typing import Any

from crypto_trendwatching.agent.tools import AgentTools
from crypto_trendwatching.domain.models import (
    AgentTurn,
    EvidenceBinding,
    OnChainObservation,
    Signal,
    TrendCandidate,
)
from crypto_trendwatching.domain.ports import LLMClient
from crypto_trendwatching.urls import normalize_url

logger = logging.getLogger(__name__)

_DEFAULT_MAX_ROUNDS = 4
_DEFAULT_MAX_TOKENS = 4096


@dataclass(frozen=True)
class ResearchResult:
    """Итог исследования кандидата: заметки + доказательства + on-chain-снимки."""

    notes: str
    evidence: list[EvidenceBinding] = field(default_factory=list)
    onchain: list[OnChainObservation] = field(default_factory=list)


class AgentLoop:
    """Агентный цикл исследования одного кандидата в тренд."""

    def __init__(
        self,
        llm: LLMClient,
        tools: AgentTools,
        *,
        max_rounds: int = _DEFAULT_MAX_ROUNDS,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> None:
        self._llm = llm
        self._tools = tools
        self._max_rounds = max_rounds
        self._max_tokens = max_tokens

    def research(
        self,
        candidate: TrendCandidate,
        signals: list[Signal],
        run_id: int,
        *,
        onchain_hint: str = "",
    ) -> ResearchResult:
        messages = self._initial_messages(candidate, signals, onchain_hint)
        evidence: list[EvidenceBinding] = []
        onchain: list[OnChainObservation] = []

        for _ in range(self._max_rounds):
            turn = self._llm.complete_with_tools(messages, self._tools.definitions())
            if not turn.tool_calls:
                return self._finalize(turn.content, evidence, onchain)
            messages.append(_assistant_message(turn))
            for call in turn.tool_calls:
                result = self._tools.call(call.name, call.arguments)
                evidence.extend(
                    replace(binding, candidate_id=candidate.id)
                    for binding in result.evidence
                )
                onchain.extend(
                    replace(obs, run_id=run_id, candidate_id=candidate.id)
                    for obs in result.onchain
                )
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": result.text}
                )

        notes = self._llm.complete(
            self._final_messages(messages), max_tokens=self._max_tokens
        )
        return self._finalize(notes, evidence, onchain)

    def _initial_messages(
        self,
        candidate: TrendCandidate,
        signals: list[Signal],
        onchain_hint: str,
    ) -> list[dict[str, Any]]:
        signal_lines = "\n".join(
            f"- {signal.title or ''} ({signal.source_id or ''}) {signal.url}"
            for signal in signals
        )
        hint = (
            f"\n\nДля on-chain-подтверждения проверь: {onchain_hint}"
            if onchain_hint
            else ""
        )
        return [
            {
                "role": "system",
                "content": (
                    "Ты — исследовательский агент по крипторынку. Изучи тренд-кандидата: "
                    "подтверди тезис первоисточниками и объективными on-chain-данными "
                    "(TVL/объёмы/цена). Используй инструменты fetch_url/search_web/check_onchain. "
                    "Затем дай итоговые заметки: тезис, подтверждающие факты, метрики, оговорки."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Тренд-кандидат: {candidate.name}\n"
                    f"Определение: {candidate.definition or ''}\n"
                    f"Зрелость: {candidate.maturity or ''}\n"
                    f"Сигналы:\n{signal_lines}{hint}"
                ),
            },
        ]

    def _final_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            *messages,
            {
                "role": "user",
                "content": (
                    "Бюджет раундов исчерпан. Сформулируй финальные исследовательские "
                    "заметки по тренду без вызова инструментов."
                ),
            },
        ]

    def _finalize(
        self,
        notes: str,
        evidence: list[EvidenceBinding],
        onchain: list[OnChainObservation],
    ) -> ResearchResult:
        return ResearchResult(
            notes=notes, evidence=_dedup_evidence(evidence), onchain=onchain
        )


def _assistant_message(turn: AgentTurn) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": turn.content or None,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments, ensure_ascii=False),
                },
            }
            for call in turn.tool_calls
        ],
    }


def _dedup_evidence(evidence: list[EvidenceBinding]) -> list[EvidenceBinding]:
    seen: set[str] = set()
    result: list[EvidenceBinding] = []
    for binding in evidence:
        if not binding.source_url:
            continue
        key = normalize_url(binding.source_url)
        if key in seen:
            continue
        seen.add(key)
        result.append(binding)
    return result
