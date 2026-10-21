"""Конвейер M3: collect → filter → cluster → research → verify → whale/интерпретация/календарь → отчёт."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any

from crypto_trendwatching.agent.loop import AgentLoop, ResearchResult
from crypto_trendwatching.agent.tools import AgentTools
from crypto_trendwatching.application.catalog import (
    SourceRef,
    catalog_snapshot,
    resolve_number,
)
from crypto_trendwatching.application.catalysts import (
    extract_catalysts,
    fetch_unlock_catalysts,
)
from crypto_trendwatching.application.circuit_breaker import CircuitBreaker
from crypto_trendwatching.application.config_loader import OnChainMapping
from crypto_trendwatching.application.docx import markdown_to_docx
from crypto_trendwatching.application.filter import filter_by_zone
from crypto_trendwatching.application.freshness import measure_velocity
from crypto_trendwatching.application.interpret import interpret_candidate
from crypto_trendwatching.application.parsing import parse_json_list
from crypto_trendwatching.application.render import ReportContext, render_report
from crypto_trendwatching.application.verify import (
    CandidateVerdict,
    Verifier,
    VerifyThresholds,
)
from crypto_trendwatching.application.whale_map import map_whale_verdict
from crypto_trendwatching.domain.models import (
    Catalyst,
    Interpretation,
    OnChainObservation,
    ReportedTrend,
    ReportRun,
    Signal,
    TrendCandidate,
    TrendVelocity,
    WhaleTransfer,
    Zone,
)
from crypto_trendwatching.domain.ports import (
    Embedder,
    LLMClient,
    OnChainClient,
    SearchProvider,
    SourceCollector,
    TrendRepository,
    WhaleClient,
)
from crypto_trendwatching.usage import TokenUsageTracker

logger = logging.getLogger(__name__)

_ZONE_THRESHOLD = 0.3
_CLUSTER_MAX_TOKENS = 8000
_CLUSTER_MAX_ATTEMPTS = 2
_CLUSTER_CHUNK_SIZE = 40
_WHALE_MIN_USD = 1_000_000


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _week_ago_iso() -> str:
    return (datetime.now(UTC) - timedelta(days=7)).isoformat()


def _signal_text(signal: Signal) -> str:
    return " ".join(part for part in (signal.title, signal.summary) if part)


def _zone_profile_text(zone: Zone) -> str:
    return " ".join([zone.name, *zone.seed_keywords])


def _short_error(exc: Exception) -> str:
    """Короткая строка ошибки для записи в report_runs.error."""
    return f"{type(exc).__name__}: {exc}"[:300]


@contextmanager
def _timing(timings: dict[str, float], name: str) -> Iterator[None]:
    start = perf_counter()
    yield
    timings[name] = round(perf_counter() - start, 4)


class Pipeline:
    """Сквозной конвейер M3: сбор → отбор → кластеризация → исследование → верификация → обогащение → отчёт."""

    def __init__(  # noqa: PLR0913, PLR0917
        self,
        collector: SourceCollector,
        repository: TrendRepository,
        embedder: Embedder,
        llm: LLMClient,
        search: SearchProvider,
        onchain: OnChainClient,
        whale: WhaleClient,
        *,
        catalog: dict[str, SourceRef] | None = None,
        onchain_mapping: dict[str, OnChainMapping] | None = None,
        liveness: Callable[[str], bool] | None = None,
        unlock_fetcher: Callable[[int], list[Catalyst]] | None = None,
        verify_thresholds: VerifyThresholds | None = None,
        research_budget_seconds: float | None = None,
        usage: TokenUsageTracker | None = None,
    ) -> None:
        self._collector = collector
        self._repository = repository
        self._embedder = embedder
        self._llm = llm
        self._search = search
        self._onchain = onchain
        self._whale = whale
        self._catalog = catalog or {}
        self._onchain_mapping = onchain_mapping or {}
        self._unlock_fetcher = unlock_fetcher or fetch_unlock_catalysts
        self._research_budget_seconds = research_budget_seconds
        self._usage = usage
        self._whale_breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=60.0)
        self._agent = AgentLoop(llm, AgentTools(search, onchain))
        self._verifier = Verifier(
            repository, embedder, llm, liveness=liveness, thresholds=verify_thresholds
        )

    def run(self, zone: Zone) -> ReportRun:
        run_id = self._repository.save_run(
            ReportRun(status="running", zone_id=zone.id, started_at=_now_iso())
        )
        return self.execute(run_id, zone)

    def execute(self, run_id: int, zone: Zone) -> ReportRun:  # noqa: PLR0915
        funnel: dict[str, Any] = {
            "zone": zone.id,
            "phases": {},
            "catalog": catalog_snapshot(self._catalog),
            "timings": {},
        }

        try:
            with _timing(funnel["timings"], "collect"):
                signals = self._collector.collect(zone)
                empty_transfers: list[WhaleTransfer] = []
                whale_transfers = (
                    self._whale_breaker.call(
                        self._whale.transfers,
                        min_usd=_WHALE_MIN_USD,
                        since=_week_ago_iso(),
                        fallback=empty_transfers,
                    )
                    or empty_transfers
                )
            funnel["phases"]["collect"] = {"signals": len(signals)}
            funnel["providers"] = {"whale_failures": self._whale_breaker.failure_count}
            self._repository.save_zone_result(
                run_id, zone.id, "collecting", {"signals": len(signals)}
            )
            for transfer in whale_transfers:
                self._repository.save_whale_transfer(run_id, transfer)
            funnel["phases"]["whale_collect"] = {"transfers": len(whale_transfers)}
            self._repository.save_zone_result(
                run_id, zone.id, "whale", {"transfers": len(whale_transfers)}
            )

            with _timing(funnel["timings"], "filter"):
                embeddings = self._embedder.embed([_signal_text(s) for s in signals])
                profile = self._embedder.embed([_zone_profile_text(zone)])[0]
                kept_indices = filter_by_zone(
                    signals, embeddings, profile, _ZONE_THRESHOLD
                )
                kept_signals = [signals[i] for i in kept_indices]
                for index in kept_indices:
                    self._repository.save_signal(signals[index], embeddings[index])
            funnel["phases"]["embed"] = {"signals": len(signals)}
            funnel["phases"]["filter"] = {"signals": len(kept_signals)}
            self._repository.save_zone_result(
                run_id, zone.id, "embedding", {"signals": len(signals)}
            )
            self._repository.save_zone_result(
                run_id, zone.id, "filtering", {"signals": len(kept_signals)}
            )

            with _timing(funnel["timings"], "synthesize"):
                candidates, candidate_signals = self._cluster(
                    zone, kept_signals, run_id
                )
            funnel["phases"]["synthesize"] = {"candidates": len(candidates)}
            self._repository.save_zone_result(
                run_id, zone.id, "synthesizing", {"candidates": len(candidates)}
            )

            with _timing(funnel["timings"], "research"):
                research = self._research(zone, candidates, candidate_signals, run_id)
            funnel["phases"]["research"] = {"candidates": len(candidates)}
            self._repository.save_zone_result(
                run_id, zone.id, "research", {"candidates": len(candidates)}
            )

            with _timing(funnel["timings"], "verify"):
                verdicts = self._verifier.verify_candidates(candidates, research)
            funnel["phases"]["verify"] = {
                "passed": sum(1 for v in verdicts if v.passed),
                "rejected_repeats": sum(1 for v in verdicts if v.is_repeat),
            }
            self._repository.save_zone_result(
                run_id, zone.id, "verify", funnel["phases"]["verify"]
            )

            with _timing(funnel["timings"], "enrich"):
                passed = [v for v in verdicts if v.passed]
                whale_verdicts = {
                    v.candidate.id or 0: map_whale_verdict(
                        self._llm, v.candidate, whale_transfers
                    )
                    for v in passed
                }
                interpretations = self._interpret(passed, research, whale_verdicts)
                catalysts = extract_catalysts(self._llm, zone, kept_signals, run_id)
                catalysts.extend(self._unlock_fetcher(run_id))
                for catalyst in catalysts:
                    self._repository.save_catalyst(catalyst)
            funnel["phases"]["catalysts"] = {"count": len(catalysts)}
            self._repository.save_zone_result(
                run_id, zone.id, "catalysts", {"count": len(catalysts)}
            )

            with _timing(funnel["timings"], "memory"):
                remembered, fresh_trends = self._remember_and_freshness(zone, verdicts)
            funnel["phases"]["memory"] = {"remembered": remembered}
            self._repository.save_zone_result(
                run_id, zone.id, "memory", {"remembered": remembered}
            )

            weak_signals = self._weak_signals(kept_signals, candidate_signals)
            funnel["phases"]["weak_signals"] = {"count": len(weak_signals)}
            if self._usage is not None:
                funnel["tokens"] = self._usage.snapshot()

            with _timing(funnel["timings"], "report"):
                report_md = render_report(
                    ReportContext(
                        zone=zone,
                        verdicts=verdicts,
                        research=research,
                        catalog=self._catalog,
                        funnel=funnel,
                        interpretations=interpretations,
                        whale_verdicts=whale_verdicts,
                        whale_transfers=whale_transfers,
                        catalysts=catalysts,
                        weak_signals=weak_signals,
                        fresh_trends=fresh_trends,
                    )
                )
                report_docx = markdown_to_docx(report_md)
            self._repository.save_zone_result(run_id, zone.id, "completed", funnel)
            self._repository.update_run(
                run_id,
                status="completed",
                finished_at=_now_iso(),
                funnel_json=json.dumps(funnel, ensure_ascii=False),
                report_md=report_md,
                report_docx=report_docx,
            )
            return ReportRun(
                id=run_id,
                status="completed",
                report_md=report_md,
                report_docx=report_docx,
                funnel_json=json.dumps(funnel, ensure_ascii=False),
            )
        except Exception as exc:
            logger.exception("прогон завершился с ошибкой для зоны %s", zone.id)
            self._repository.update_run(
                run_id,
                status="failed",
                finished_at=_now_iso(),
                error=_short_error(exc),
            )
            raise

    def _cluster(
        self, zone: Zone, signals: list[Signal], run_id: int
    ) -> tuple[list[TrendCandidate], dict[int, list[Signal]]]:
        if not signals:
            return [], {}
        candidates: list[TrendCandidate] = []
        candidate_signals: dict[int, list[Signal]] = {}
        for start in range(0, len(signals), _CLUSTER_CHUNK_SIZE):
            chunk = signals[start : start + _CLUSTER_CHUNK_SIZE]
            for candidate, indices in self._cluster_chunk(
                zone, chunk, start, signals, run_id
            ):
                candidates.append(candidate)
                if candidate.id is not None:
                    candidate_signals[candidate.id] = [signals[i] for i in indices]
        return candidates, candidate_signals

    def _cluster_chunk(
        self,
        zone: Zone,
        chunk: list[Signal],
        start: int,
        signals: list[Signal],
        run_id: int,
    ) -> list[tuple[TrendCandidate, list[int]]]:
        items = "\n".join(
            f"[{start + i}] {s.title or ''} — {s.summary or ''} (source={s.source_id})"
            for i, s in enumerate(chunk)
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "Ты аналитик крипторынка. Сгруппируй сигналы в тренды-кандидаты. "
                    "Верни только JSON-массив объектов: "
                    '[{"name": str, "definition": str, "maturity": str, "signal_indices": [int]}]. '
                    "maturity ∈ {зарождающийся, растущий, устоявшийся, угасающий}. "
                    "Без пояснений и markdown — только валидный JSON."
                ),
            },
            {"role": "user", "content": f"Зона: {zone.name}\n\nСигналы:\n{items}"},
        ]

        for attempt in range(_CLUSTER_MAX_ATTEMPTS):
            raw = self._llm.complete(messages, max_tokens=_CLUSTER_MAX_TOKENS)
            parsed = parse_json_list(raw)
            if parsed:
                return self._build_candidates(parsed, signals, run_id)
            logger.warning(
                "кластеризация вернула пустой результат (попытка %d/%d)",
                attempt + 1,
                _CLUSTER_MAX_ATTEMPTS,
            )
        return []

    def _build_candidates(
        self, parsed: list[dict[str, Any]], signals: list[Signal], run_id: int
    ) -> list[tuple[TrendCandidate, list[int]]]:
        result: list[tuple[TrendCandidate, list[int]]] = []
        for item in parsed:
            indices = [
                int(i)
                for i in item.get("signal_indices", [])
                if isinstance(i, int) and 0 <= i < len(signals)
            ]
            catalog_numbers: set[int] = set()
            for i in indices:
                number = resolve_number(self._catalog, signals[i].source_id)
                if number is not None:
                    catalog_numbers.add(number)
            candidate = TrendCandidate(
                run_id=run_id,
                name=str(item.get("name") or ""),
                definition=item.get("definition"),
                maturity=item.get("maturity"),
                catalog_numbers=sorted(catalog_numbers),
            )
            candidate_id = self._repository.save_trend_candidate(candidate)
            candidate = TrendCandidate(
                run_id=run_id,
                name=candidate.name,
                definition=candidate.definition,
                maturity=candidate.maturity,
                catalog_numbers=candidate.catalog_numbers,
                id=candidate_id,
            )
            result.append((candidate, indices))
        return result

    def _research(
        self,
        zone: Zone,
        candidates: list[TrendCandidate],
        candidate_signals: dict[int, list[Signal]],
        run_id: int,
    ) -> dict[int, ResearchResult]:
        hint = self._onchain_hint(zone)
        research: dict[int, ResearchResult] = {}
        budget = self._research_budget_seconds
        started = perf_counter()
        budget_hit = False
        for candidate in candidates:
            if candidate.id is None:
                continue
            if budget is not None and perf_counter() - started > budget:
                if not budget_hit:
                    logger.warning("бюджет research исчерпан (%.0fс)", budget)
                    budget_hit = True
                research[candidate.id] = ResearchResult(notes="")
                continue
            signals = candidate_signals.get(candidate.id, [])
            result = self._agent.research(candidate, signals, run_id, onchain_hint=hint)
            for observation in result.onchain:
                self._repository.save_onchain_observation(observation)
            research[candidate.id] = result
        return research

    def _interpret(
        self,
        passed: list[CandidateVerdict],
        research: dict[int, ResearchResult],
        whale_verdicts: dict[int, str | None],
    ) -> dict[int, Interpretation]:
        interpretations: dict[int, Interpretation] = {}
        for verdict in passed:
            candidate_id = verdict.candidate.id or 0
            result = research.get(candidate_id)
            observations = result.onchain if result is not None else []
            interpretations[candidate_id] = interpret_candidate(
                self._llm,
                verdict.candidate,
                _onchain_text(observations),
                whale_verdicts.get(candidate_id),
            )
        return interpretations

    def _onchain_hint(self, zone: Zone) -> str:
        mapping = self._onchain_mapping.get(zone.id)
        if mapping is None:
            return ""
        parts = []
        if mapping.coins:
            parts.append(f"монеты: {', '.join(mapping.coins)}")
        if mapping.protocols:
            parts.append(f"протоколы: {', '.join(mapping.protocols)}")
        return "; ".join(parts)

    def _remember_and_freshness(
        self, zone: Zone, verdicts: list[CandidateVerdict]
    ) -> tuple[int, list[tuple[ReportedTrend, list[TrendVelocity]]]]:
        now = _now_iso()
        mapping = self._onchain_mapping.get(zone.id)
        remembered = 0
        for verdict in verdicts:
            if verdict.passed:
                trend_id = self._repository.save_reported_trend(
                    ReportedTrend(
                        name=verdict.candidate.name,
                        definition=verdict.candidate.definition,
                        maturity=verdict.candidate.maturity,
                        embedding=verdict.embedding,
                        first_reported_at=now,
                        last_reported_at=now,
                    )
                )
                measure_velocity(
                    self._repository, self._onchain, trend_id, mapping, now
                )
                remembered += 1
            elif verdict.is_repeat and verdict.repeat_id is not None:
                measure_velocity(
                    self._repository, self._onchain, verdict.repeat_id, mapping, now
                )
        fresh: list[tuple[ReportedTrend, list[TrendVelocity]]] = []
        for trend in self._repository.list_reported_trends():
            if trend.id is None:
                continue
            velocities = self._repository.list_trend_velocity(trend.id)
            if velocities:
                fresh.append((trend, velocities))
        return remembered, fresh

    def _weak_signals(
        self,
        kept_signals: list[Signal],
        candidate_signals: dict[int, list[Signal]],
    ) -> list[Signal]:
        used_urls = {s.url for signals in candidate_signals.values() for s in signals}
        return [s for s in kept_signals if s.url not in used_urls]


def _onchain_text(observations: list[OnChainObservation]) -> str:
    if not observations:
        return "нет данных"
    parts = []
    for observation in observations:
        value = f"{observation.value:,.0f}" if observation.value is not None else "—"
        change = (
            f" (7д {observation.change_7d:+.1f}%)"
            if observation.change_7d is not None
            else ""
        )
        parts.append(f"{observation.metric} {observation.subject}: {value}{change}")
    return "; ".join(parts)
