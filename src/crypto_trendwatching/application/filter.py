"""Отбор по зоне: нормализация URL, косинусная близость, фильтр."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from crypto_trendwatching.domain.models import Signal
from crypto_trendwatching.urls import normalize_url

Embedding = npt.NDArray[np.float16]

__all__ = ["cosine_similarity", "filter_by_zone", "normalize_url"]


def cosine_similarity(left: Embedding, right: Embedding) -> float:
    """Косинусная близость двух векторов (устойчиво к ненормированным)."""
    a = np.asarray(left, dtype=np.float32).ravel()
    b = np.asarray(right, dtype=np.float32).ravel()
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def filter_by_zone(
    signals: list[Signal],
    embeddings: Embedding,
    profile: Embedding,
    threshold: float,
) -> list[int]:
    """Индексы сигналов после дедупа по URL и отсева ниже порога близости к зоне."""
    kept: list[int] = []
    seen: set[str] = set()
    for index, signal in enumerate(signals):
        if not signal.url:
            continue
        key = normalize_url(signal.url)
        if key in seen:
            continue
        if cosine_similarity(embeddings[index], profile) < threshold:
            continue
        seen.add(key)
        kept.append(index)
    return kept
