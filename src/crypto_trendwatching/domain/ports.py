"""Порты (Protocols) — швы гексагональной архитектуры."""

from __future__ import annotations

from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

from crypto_trendwatching.domain.models import (
    AgentTurn,
    Catalyst,
    EvidenceBinding,
    EvidenceVerdict,
    OnChainObservation,
    ReportedTrend,
    ReportRun,
    SearchResult,
    Signal,
    Tool,
    TrendCandidate,
    TrendVelocity,
    WhaleTransfer,
    Zone,
)

Embedding = npt.NDArray[np.float16]


class LLMClient(Protocol):
    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Any = None,
        max_tokens: int | None = None,
    ) -> str: ...

    def complete_with_tools(
        self, messages: list[dict[str, Any]], tools: list[Tool]
    ) -> AgentTurn: ...


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> Embedding: ...


class SearchProvider(Protocol):
    def search(self, query: str, *, limit: int = 10) -> list[SearchResult]: ...


class SourceCollector(Protocol):
    def collect(self, zone: Zone) -> list[Signal]: ...


class OnChainClient(Protocol):
    def tvl(self, protocol: str) -> float: ...

    def volume(self, protocol: str, window: str) -> float: ...

    def price(self, coin: str) -> float: ...

    def change(self, metric: str, subject: str, window_days: int) -> float | None: ...


class WhaleClient(Protocol):
    def transfers(
        self, *, min_usd: float, since: str | None = None
    ) -> list[WhaleTransfer]: ...


class TrendRepository(Protocol):
    def save_signal(self, s: Signal, embedding: Embedding | None = None) -> int: ...

    def list_signals(self, zone_id: str) -> list[Signal]: ...

    def save_reported_trend(self, t: ReportedTrend) -> int: ...

    def list_reported_trends(self) -> list[ReportedTrend]: ...

    def save_trend_candidate(self, candidate: TrendCandidate) -> int: ...

    def list_trend_candidates(self, run_id: int) -> list[TrendCandidate]: ...

    def save_evidence_binding(self, binding: EvidenceBinding) -> int: ...

    def list_evidence_bindings(self, candidate_id: int) -> list[EvidenceBinding]: ...

    def save_evidence_verdict(self, verdict: EvidenceVerdict) -> int: ...

    def list_evidence_verdicts(self, candidate_id: int) -> list[EvidenceVerdict]: ...

    def save_onchain_observation(self, observation: OnChainObservation) -> int: ...

    def list_onchain_observations(
        self, candidate_id: int
    ) -> list[OnChainObservation]: ...

    def list_onchain_observations_by_run(
        self, run_id: int
    ) -> list[OnChainObservation]: ...

    def list_pump_flagged_candidates(self) -> list[TrendCandidate]: ...

    def save_whale_transfer(self, run_id: int, transfer: WhaleTransfer) -> int: ...

    def list_whale_transfers(self, run_id: int) -> list[WhaleTransfer]: ...

    def save_catalyst(self, catalyst: Catalyst) -> int: ...

    def list_catalysts(self, run_id: int) -> list[Catalyst]: ...

    def upsert_trend_velocity(
        self,
        trend_id: int,
        metric: str,
        subject: str,
        value: float,
        measured_at: str,
    ) -> TrendVelocity: ...

    def list_trend_velocity(self, trend_id: int) -> list[TrendVelocity]: ...

    def save_run(self, run: ReportRun) -> int: ...

    def update_run(self, run_id: int, **kwargs: Any) -> None: ...

    def get_run(self, run_id: int) -> ReportRun | None: ...

    def list_runs(self) -> list[ReportRun]: ...

    def delete_run(self, run_id: int) -> bool: ...

    def save_zone_result(
        self,
        run_id: int,
        zone_id: str,
        status: str,
        checkpoint: dict[str, Any] | None = None,
    ) -> int: ...
