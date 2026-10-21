"""Анти-повтор (novelty-gate): косинусная близость кандидата к памяти reported_trends."""

from __future__ import annotations

from dataclasses import dataclass

from crypto_trendwatching.application.filter import cosine_similarity
from crypto_trendwatching.domain.models import ReportedTrend, TrendCandidate
from crypto_trendwatching.domain.ports import Embedding

DEFAULT_ANTI_REPEAT_THRESHOLD = 0.85


@dataclass(frozen=True)
class NoveltyResult:
    """Результат novelty-gate против памяти."""

    is_repeat: bool
    repeat_of: str | None = None
    similarity: float = 0.0
    repeat_id: int | None = None


def candidate_text(candidate: TrendCandidate) -> str:
    """Текст, по которому считается эмбеддинг кандидата для анти-повтора."""
    return " ".join(
        part for part in (candidate.name, candidate.definition or "") if part
    )


def find_repeat(
    candidate_embedding: Embedding,
    reported_trends: list[ReportedTrend],
    threshold: float = DEFAULT_ANTI_REPEAT_THRESHOLD,
) -> NoveltyResult:
    """Вернуть повтор из памяти, если косинусная близость >= порога."""
    best_name: str | None = None
    best_similarity = 0.0
    best_id: int | None = None
    for trend in reported_trends:
        if trend.embedding is None:
            continue
        similarity = cosine_similarity(candidate_embedding, trend.embedding)
        if similarity > best_similarity:
            best_similarity = similarity
            best_name = trend.name
            best_id = trend.id
    if best_name is not None and best_similarity >= threshold:
        return NoveltyResult(
            is_repeat=True,
            repeat_of=best_name,
            similarity=best_similarity,
            repeat_id=best_id,
        )
    return NoveltyResult(is_repeat=False, similarity=best_similarity)
