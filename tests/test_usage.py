"""Tests for the token usage tracker."""

from crypto_trendwatching.usage import TokenUsageTracker


def test_tracker_accumulates() -> None:
    tracker = TokenUsageTracker()
    tracker.add(10, 5)
    tracker.add(20, 15)
    assert tracker.prompt_tokens == 30
    assert tracker.completion_tokens == 20
    assert tracker.total_tokens == 50
    assert tracker.snapshot() == {
        "prompt_tokens": 30,
        "completion_tokens": 20,
        "total_tokens": 50,
    }


def test_tracker_ignores_negatives() -> None:
    tracker = TokenUsageTracker()
    tracker.add(-5, -3)
    assert tracker.prompt_tokens == 0
    assert tracker.completion_tokens == 0
