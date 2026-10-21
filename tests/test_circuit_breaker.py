"""Tests for the circuit breaker."""

from __future__ import annotations

from crypto_trendwatching.application.circuit_breaker import CircuitBreaker


def test_breaker_opens_after_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=60.0)

    def fail() -> str:
        raise RuntimeError("boom")

    assert breaker.call(fail, fallback="x") == "x"
    assert breaker.call(fail, fallback="x") == "x"
    assert breaker.failure_count == 2
    assert breaker.is_open() is True
    # пока цепь открыта — вызов не выполняется, возвращается fallback
    assert breaker.call(lambda: "ok", fallback="y") == "y"


def test_breaker_resets_on_success() -> None:
    breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=60.0)

    assert breaker.call(lambda: "ok") == "ok"
    assert breaker.failure_count == 0
    assert breaker.is_open() is False


def test_breaker_success_after_failures_without_opening() -> None:
    breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=60.0)

    def flaky() -> str:
        raise RuntimeError("boom")

    assert breaker.call(flaky, fallback="x") == "x"
    assert breaker.call(flaky, fallback="x") == "x"
    assert breaker.call(lambda: "ok") == "ok"
    assert breaker.is_open() is False
