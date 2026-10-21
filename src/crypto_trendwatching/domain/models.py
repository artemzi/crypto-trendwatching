"""Domain models: frozen config models and dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, Field, model_validator

Method = Literal["rss", "fetch_url", "search", "onchain_api", "whale_api"]


class Zone(BaseModel):
    """Наблюдаемая зона крипторынка (из config/topics.yaml)."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    enabled: bool = True
    seed_keywords: list[str] = Field(default_factory=list)
    onchain_indicators: list[str] = Field(default_factory=list)


class Source(BaseModel):
    """Источник данных (из config/sources.yaml)."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str
    name: str
    url: str
    region: str
    method: Method
    availability_from_rf: str
    feed_url: str | None = None
    enabled: bool = True
    notes: str | None = None
    category: str = ""

    @model_validator(mode="after")
    def _require_feed_url_for_rss(self) -> Source:
        if self.method == "rss" and not self.feed_url:
            raise ValueError(f"rss-источник {self.id} требует feed_url")
        return self


@dataclass(frozen=True)
class Signal:
    """Собранный элемент (RSS/поиск/fetch_url) до обработки."""

    url: str
    source_id: str | None = None
    zone_id: str | None = None
    title: str | None = None
    summary: str | None = None
    published_at: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchResult:
    """Результат поискового провайдера."""

    provider: str
    url: str
    title: str | None = None
    snippet: str | None = None


@dataclass(frozen=True)
class TrendCandidate:
    """Кандидат в тренд, собранный из сигналов."""

    run_id: int
    name: str
    definition: str | None = None
    maturity: str | None = None
    catalog_numbers: list[int] = field(default_factory=list)
    id: int | None = None


@dataclass(frozen=True)
class ReportedTrend:
    """Тренд из памяти (анти-повтор)."""

    name: str
    definition: str | None = None
    maturity: str | None = None
    embedding: npt.NDArray[np.float16] | None = None
    first_reported_at: str | None = None
    last_reported_at: str | None = None
    id: int | None = None


@dataclass(frozen=True)
class EvidenceBinding:
    """Привязка цитаты к источнику (append-only)."""

    source_url: str
    quote: str | None = None
    catalog_number: int | None = None
    candidate_id: int | None = None


@dataclass(frozen=True)
class EvidenceVerdict:
    """Вердикт проверки (append-only). Привязывается к цитате и/или кандидату."""

    verdict: str
    reason: str | None = None
    binding_id: int | None = None
    candidate_id: int | None = None


@dataclass(frozen=True)
class OnChainObservation:
    """Снимок on-chain-метрики (TVL/объём/цена) для кандидата или прогона."""

    run_id: int
    metric: str
    subject: str
    value: float | None = None
    change_7d: float | None = None
    change_30d: float | None = None
    observed_at: str | None = None
    candidate_id: int | None = None


@dataclass(frozen=True)
class ToolCall:
    """Вызов инструмента, который LLM попросил выполнить в agentic loop."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentTurn:
    """Результат хода LLM: текст и/или вызовы инструментов."""

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass(frozen=True)
class Tool:
    """Описание инструмента для LLM (JSON-schema параметров)."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WhaleTransfer:
    """Крупный трансфер / активность smart money."""

    amount_usd: float = 0.0
    asset: str | None = None
    from_address: str | None = None
    to_address: str | None = None
    timestamp: str | None = None


@dataclass(frozen=True)
class Interpretation:
    """Блок инвестиционной интерпретации тренда (D-04)."""

    direction: str | None = None
    horizon: str | None = None
    catalysts: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    onchain_status: str | None = None
    disclaimer: str | None = None


@dataclass(frozen=True)
class Catalyst:
    """Событие катализатор-календаря (FR-9)."""

    run_id: int
    title: str
    event_date: str | None = None
    category: str | None = None
    candidate_id: int | None = None
    source_url: str | None = None


@dataclass(frozen=True)
class TrendVelocity:
    """Freshness-снимок тренда (FR-11, D-12.4): дельта цены/TVL с первого сигнала."""

    trend_id: int
    metric: str
    subject: str
    first_value: float | None = None
    last_value: float | None = None
    measured_at: str | None = None


@dataclass(frozen=True)
class ReportRun:
    """Прогон конвейера и его результат."""

    status: str
    zone_id: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    funnel_json: str | None = None
    report_md: str | None = None
    report_docx: bytes | None = None
    error: str | None = None
    id: int | None = None
