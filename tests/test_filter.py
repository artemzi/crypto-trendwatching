"""Tests for URL normalization and zone filtering."""

import numpy as np
import pytest

from crypto_trendwatching.application.filter import (
    cosine_similarity,
    filter_by_zone,
    normalize_url,
)
from crypto_trendwatching.domain.models import Signal


def test_normalize_url_strips_www_tracking_and_fragment() -> None:
    url = "HTTPS://WWW.Example.com/path/?utm_source=x&y=2#frag"
    assert normalize_url(url) == "https://example.com/path?y=2"


def test_normalize_url_strips_trailing_slash() -> None:
    assert normalize_url("https://example.com/news/") == "https://example.com/news"


def test_cosine_identical_is_one() -> None:
    vector = np.array([1.0, 2.0, 3.0], dtype=np.float16)
    assert cosine_similarity(vector, vector) == pytest.approx(1.0)


def test_cosine_orthogonal_is_zero() -> None:
    left = np.array([1.0, 0.0], dtype=np.float16)
    right = np.array([0.0, 1.0], dtype=np.float16)
    assert cosine_similarity(left, right) == pytest.approx(0.0)


def test_filter_by_zone_keeps_relevant_and_dedups() -> None:
    profile = np.array([[1.0, 0.0]], dtype=np.float16)[0]
    embeddings = np.array(
        [
            [1.0, 0.0],
            [0.0, 1.0],
            [1.0, 0.0],
        ],
        dtype=np.float16,
    )
    signals = [
        Signal(url="https://a.com/1"),
        Signal(url="https://b.com/2"),
        Signal(url="https://a.com/1?utm_source=x"),
    ]
    kept = filter_by_zone(signals, embeddings, profile, threshold=0.5)
    assert kept == [0]
