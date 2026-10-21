"""Верификационная цепочка M2: живость → анти-повтор → релевантность → обоснованность → pump."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from crypto_trendwatching.agent.loop import ResearchResult
from crypto_trendwatching.application.anti_repeat import (
    DEFAULT_ANTI_REPEAT_THRESHOLD,
    candidate_text,
    find_repeat,
)
from crypto_trendwatching.domain.models import (
    EvidenceBinding,
    EvidenceVerdict,
    ReportedTrend,
    TrendCandidate,
)
from crypto_trendwatching.domain.ports import (
    Embedder,
    Embedding,
    LLMClient,
    TrendRepository,
)

logger = logging.getLogger(__name__)

_SUCCESS_STATUS_BOUND = 400


@dataclass(frozen=True)
class VerifyThresholds:
    """Пороги верификации (D-07, D-08)."""

    anti_repeat_cosine: float = DEFAULT_ANTI_REPEAT_THRESHOLD
    pump_price_change_7d: float = 30.0
    confirmation_change: float = 10.0


@dataclass(frozen=True)
class CandidateVerdict:
    """Итог верификации одного кандидата."""

    candidate: TrendCandidate
    passed: bool
    is_repeat: bool = False
    repeat_of: str | None = None
    repeat_id: int | None = None
    pump: bool = False
    live_evidence: int = 0
    embedding: Embedding | None = None
    bindings: list[EvidenceBinding] = field(default_factory=list)
    verdicts: list[EvidenceVerdict] = field(default_factory=list)


def check_url_liveness(url: str, *, timeout: float = 10.0) -> bool:
    """Проверка живости URL (HEAD, при неудаче — GET). Fail-open: ошибка → False."""
    if not url:
        return False
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            try:
                response = client.head(url)
                if response.status_code in {400, 405, 501}:
                    response = client.get(url)
            except httpx.HTTPError:
                response = client.get(url)
            return response.status_code < _SUCCESS_STATUS_BOUND
    except Exception:
        logger.exception("проверка живости URL не удалась: %s", url)
        return False


class Verifier:
    """Упорядоченная верификационная цепочка для кандидатов в тренд."""

    def __init__(
        self,
        repository: TrendRepository,
        embedder: Embedder,
        llm: LLMClient,
        *,
        thresholds: VerifyThresholds | None = None,
        liveness: Callable[[str], bool] | None = None,
    ) -> None:
        self._repository = repository
        self._embedder = embedder
        self._llm = llm
        self._thresholds = thresholds or VerifyThresholds()
        self._liveness = liveness or check_url_liveness

    def verify_candidates(
        self,
        candidates: list[TrendCandidate],
        research: dict[int, ResearchResult],
    ) -> list[CandidateVerdict]:
        reported = self._repository.list_reported_trends()
        return [
            self._verify_candidate(candidate, research, reported)
            for candidate in candidates
        ]

    def _verify_candidate(
        self,
        candidate: TrendCandidate,
        research: dict[int, ResearchResult],
        reported: list[ReportedTrend],
    ) -> CandidateVerdict:
        embedding = self._embedder.embed([candidate_text(candidate)])[0]
        result = research.get(candidate.id or 0)
        evidence = result.evidence if result is not None else []

        novelty = find_repeat(embedding, reported, self._thresholds.anti_repeat_cosine)
        if novelty.is_repeat:
            self._repository.save_evidence_verdict(
                EvidenceVerdict(
                    verdict="repeat",
                    reason=f"совпадает с ранее замеченным «{novelty.repeat_of}» "
                    f"(косинус {novelty.similarity:.2f})",
                    candidate_id=candidate.id,
                )
            )
            return CandidateVerdict(
                candidate=candidate,
                passed=False,
                is_repeat=True,
                repeat_of=novelty.repeat_of,
                repeat_id=novelty.repeat_id,
                embedding=embedding,
            )

        bindings = self._save_bindings(evidence, candidate)
        verdicts = self._binding_verdicts(bindings, candidate)
        verdicts.append(self._judge_soundness(candidate, bindings))
        pump = self._pump_flag(result)
        verdicts.append(
            EvidenceVerdict(
                verdict="pump" if pump else "not_pump",
                reason="нарратив без on-chain-подтверждения" if pump else None,
                candidate_id=candidate.id,
            )
        )
        for verdict in verdicts:
            self._repository.save_evidence_verdict(verdict)

        live_evidence = sum(1 for verdict in verdicts if verdict.verdict == "live")
        return CandidateVerdict(
            candidate=candidate,
            passed=True,
            pump=pump,
            live_evidence=live_evidence,
            embedding=embedding,
            bindings=[binding for binding, _ in bindings],
            verdicts=verdicts,
        )

    def _save_bindings(
        self, evidence: list[EvidenceBinding], candidate: TrendCandidate
    ) -> list[tuple[EvidenceBinding, int]]:
        saved: list[tuple[EvidenceBinding, int]] = []
        for binding in evidence:
            binding_id = self._repository.save_evidence_binding(
                EvidenceBinding(
                    source_url=binding.source_url,
                    quote=binding.quote,
                    catalog_number=binding.catalog_number,
                    candidate_id=candidate.id,
                )
            )
            saved.append((binding, binding_id))
        return saved

    def _binding_verdicts(
        self, bindings: list[tuple[EvidenceBinding, int]], candidate: TrendCandidate
    ) -> list[EvidenceVerdict]:
        verdicts: list[EvidenceVerdict] = []
        for binding, binding_id in bindings:
            alive = self._liveness(binding.source_url)
            verdicts.append(
                EvidenceVerdict(
                    verdict="live" if alive else "dead",
                    reason=None if alive else "URL недоступен",
                    binding_id=binding_id,
                    candidate_id=candidate.id,
                )
            )
            verdict, reason = self._judge_relevance(candidate, binding)
            verdicts.append(
                EvidenceVerdict(
                    verdict=verdict,
                    reason=reason,
                    binding_id=binding_id,
                    candidate_id=candidate.id,
                )
            )
        return verdicts

    def _judge_relevance(
        self, candidate: TrendCandidate, binding: EvidenceBinding
    ) -> tuple[str, str | None]:
        return self._judge(
            "Оцени, подтверждает ли цитата тезис тренда. "
            'Верни только JSON: {"verdict": "relevant"|"irrelevant"|"unknown", "reason": "..."}',
            f"Тезис: {candidate.name} — {candidate.definition or ''}\n"
            f"Цитата: {binding.quote or ''}\nИсточник: {binding.source_url}",
        )

    def _judge_soundness(
        self, candidate: TrendCandidate, bindings: list[tuple[EvidenceBinding, int]]
    ) -> EvidenceVerdict:
        quotes = "\n".join(
            f"- {binding.source_url}: {binding.quote or ''}" for binding, _ in bindings
        )
        verdict, reason = self._judge(
            "Оцени, обоснован ли тезис собранными доказательствами. "
            'Верни только JSON: {"verdict": "sound"|"unsound"|"unknown", "reason": "..."}',
            f"Тезис: {candidate.name} — {candidate.definition or ''}\nДоказательства:\n{quotes}",
        )
        return EvidenceVerdict(
            verdict=verdict, reason=reason, candidate_id=candidate.id
        )

    def _judge(self, prompt: str, user: str) -> tuple[str, str | None]:
        try:
            raw = self._llm.complete(
                [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user},
                ],
                max_tokens=256,
            )
            data = _parse_verdict_json(raw)
            if isinstance(data, dict) and "verdict" in data:
                reason = data.get("reason")
                return str(data["verdict"]), str(reason) if reason else None
        except Exception:
            logger.exception("LLM-судья вернул невалидный ответ")
        return "unknown", None

    def _pump_flag(self, result: ResearchResult | None) -> bool:
        if result is None:
            return False
        price_change: float | None = None
        tvl_volume_change: float | None = None
        for observation in result.onchain:
            if observation.change_7d is None:
                continue
            if observation.metric == "price":
                price_change = _max_or_keep(price_change, observation.change_7d)
            elif observation.metric in {"tvl", "volume"}:
                tvl_volume_change = _max_or_keep(
                    tvl_volume_change, observation.change_7d
                )
        if price_change is None or price_change < self._thresholds.pump_price_change_7d:
            return False
        return (
            tvl_volume_change is None
            or tvl_volume_change < self._thresholds.confirmation_change
        )


def _parse_verdict_json(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    data = _loads_or_none(text)
    if data is not None:
        return data
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end < start:
        return None
    return _loads_or_none(text[start : end + 1])


def _loads_or_none(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _max_or_keep(current: float | None, value: float) -> float:
    return value if current is None else max(current, value)
