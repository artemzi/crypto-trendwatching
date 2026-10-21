"""Инструменты agentic loop: fetch_url / search_web / check_onchain."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from crypto_trendwatching.domain.models import (
    EvidenceBinding,
    OnChainObservation,
    Tool,
)
from crypto_trendwatching.domain.ports import OnChainClient, SearchProvider

logger = logging.getLogger(__name__)

_MAX_FETCH_CHARS = 20_000


@dataclass(frozen=True)
class ToolResult:
    """Результат вызова инструмента: текст для LLM + структурированные доказательства."""

    text: str
    evidence: list[EvidenceBinding] = field(default_factory=list)
    onchain: list[OnChainObservation] = field(default_factory=list)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class AgentTools:
    """Реестр инструментов, доступных LLM в agentic loop."""

    def __init__(
        self,
        search: SearchProvider,
        onchain: OnChainClient,
        *,
        timeout: float = 20.0,
    ) -> None:
        self._search = search
        self._onchain = onchain
        self._timeout = timeout

    def definitions(self) -> list[Tool]:
        return [
            Tool(
                name="fetch_url",
                description="Загрузить страницу по URL и вернуть её текст (до 20К символов).",
                parameters={
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                },
            ),
            Tool(
                name="search_web",
                description="Найти страницы по запросу (возвращает url/title/snippet).",
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            ),
            Tool(
                name="check_onchain",
                description=(
                    "Получить on-chain-метрику: tvl/volume (DefiLlama) или price (CoinGecko)."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "metric": {
                            "type": "string",
                            "enum": ["tvl", "volume", "price"],
                        },
                        "subject": {"type": "string"},
                    },
                    "required": ["metric", "subject"],
                },
            ),
        ]

    def call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        if name == "fetch_url":
            return self._fetch_url(str(arguments.get("url", "")))
        if name == "search_web":
            return self._search_web(str(arguments.get("query", "")))
        if name == "check_onchain":
            return self._check_onchain(
                str(arguments.get("metric", "")), str(arguments.get("subject", ""))
            )
        return ToolResult(text=f"неизвестный инструмент: {name}")

    def _fetch_url(self, url: str) -> ToolResult:
        if not url:
            return ToolResult(text="пустой URL")
        try:
            with httpx.Client(timeout=self._timeout, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
                text = response.text[:_MAX_FETCH_CHARS]
        except Exception:
            logger.exception("fetch_url не удался: %s", url)
            return ToolResult(text=f"не удалось загрузить {url}")
        return ToolResult(
            text=f"Содержимое {url}:\n{text}",
            evidence=[EvidenceBinding(source_url=url, quote=text[:500] or None)],
        )

    def _search_web(self, query: str) -> ToolResult:
        if not query:
            return ToolResult(text="пустой запрос")
        results = self._search.search(query, limit=5)
        if not results:
            return ToolResult(text="по запросу ничего не найдено")
        lines = []
        evidence: list[EvidenceBinding] = []
        for result in results:
            lines.append(f"- {result.title or ''}: {result.url}")
            if result.snippet:
                lines.append(f"  {result.snippet}")
            evidence.append(
                EvidenceBinding(source_url=result.url, quote=result.snippet)
            )
        return ToolResult(text="\n".join(lines), evidence=evidence)

    def _check_onchain(self, metric: str, subject: str) -> ToolResult:
        if not metric or not subject:
            return ToolResult(text="нужны metric и subject")
        observation = self._observe(metric, subject)
        text = (
            f"on-chain {metric}({subject}): value={observation.value}, "
            f"change_7d={observation.change_7d}, change_30d={observation.change_30d}"
        )
        return ToolResult(text=text, onchain=[observation])

    def _observe(self, metric: str, subject: str) -> OnChainObservation:
        if metric == "tvl":
            return OnChainObservation(
                run_id=0,
                metric=metric,
                subject=subject,
                value=self._onchain.tvl(subject),
                change_7d=self._onchain.change("tvl", subject, 7),
                change_30d=self._onchain.change("tvl", subject, 30),
                observed_at=_now_iso(),
            )
        if metric == "volume":
            return OnChainObservation(
                run_id=0,
                metric=metric,
                subject=subject,
                value=self._onchain.volume(subject, "7d"),
                change_7d=self._onchain.change("volume", subject, 7),
                change_30d=self._onchain.change("volume", subject, 30),
                observed_at=_now_iso(),
            )
        return OnChainObservation(
            run_id=0,
            metric=metric,
            subject=subject,
            value=self._onchain.price(subject),
            change_7d=self._onchain.change("price", subject, 7),
            change_30d=self._onchain.change("price", subject, 30),
            observed_at=_now_iso(),
        )
