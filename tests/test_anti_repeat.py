"""Tests for the anti-repeat (novelty-gate)."""

import numpy as np

from crypto_trendwatching.application.anti_repeat import candidate_text, find_repeat
from crypto_trendwatching.domain.models import ReportedTrend, TrendCandidate


def _candidate(name: str, definition: str = "") -> TrendCandidate:
    return TrendCandidate(run_id=1, name=name, definition=definition)


def test_candidate_text_joins_name_and_definition() -> None:
    assert candidate_text(_candidate("foo", "bar")) == "foo bar"
    assert candidate_text(_candidate("foo")) == "foo"


def test_find_repeat_detects_identical_embedding() -> None:
    embedding = np.array([1.0, 2.0, 3.0], dtype=np.float16)
    reported = [
        ReportedTrend(name="ранее", definition="x", embedding=embedding),
    ]
    result = find_repeat(embedding, reported, threshold=0.85)
    assert result.is_repeat is True
    assert result.repeat_of == "ранее"


def test_find_repeat_ignores_orthogonal_embedding() -> None:
    reported = [
        ReportedTrend(
            name="ранее",
            embedding=np.array([1.0, 0.0], dtype=np.float16),
        )
    ]
    candidate = np.array([0.0, 1.0], dtype=np.float16)
    result = find_repeat(candidate, reported, threshold=0.85)
    assert result.is_repeat is False


def test_find_repeat_skips_missing_embedding() -> None:
    reported = [ReportedTrend(name="без эмбеддинга", embedding=None)]
    result = find_repeat(
        np.array([1.0, 0.0], dtype=np.float16), reported, threshold=0.85
    )
    assert result.is_repeat is False
