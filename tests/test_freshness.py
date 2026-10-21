"""Tests for freshness-decay (FR-11)."""

from __future__ import annotations

from pathlib import Path

import pytest

from crypto_trendwatching.adapters.sqlite_repository import SqliteRepository
from crypto_trendwatching.application.config_loader import OnChainMapping
from crypto_trendwatching.application.freshness import delta_percent, measure_velocity
from crypto_trendwatching.domain.models import TrendVelocity


class _FakeOnChain:
    def tvl(self, _protocol: str) -> float:
        return 200.0

    def volume(self, _protocol: str, _window: str) -> float:
        return 0.0

    def price(self, _coin: str) -> float:
        return 100.0

    def change(self, _metric: str, _subject: str, _window_days: int) -> float | None:
        return None


def test_measure_velocity_upserts_and_updates(tmp_path: Path) -> None:
    repo = SqliteRepository(tmp_path / "test.db")
    mapping = OnChainMapping(zone_id="defi", coins=["aave"], protocols=["aave"])

    first = measure_velocity(
        repo, _FakeOnChain(), 1, mapping, "2026-10-14T00:00:00+00:00"
    )
    assert len(first) == 2
    assert all(v.first_value == v.last_value for v in first)

    # второй снимок обновляет last_value, сохраняя first_value
    updated = measure_velocity(
        repo, _FakeOnChain(), 1, mapping, "2026-10-21T00:00:00+00:00"
    )
    price = next(v for v in updated if v.metric == "price")
    assert price.first_value == price.last_value
    repo.close()


def test_delta_percent() -> None:
    velocity = TrendVelocity(
        trend_id=1,
        metric="price",
        subject="aave",
        first_value=100.0,
        last_value=130.0,
        measured_at="2026-10-21",
    )
    assert delta_percent(velocity) == pytest.approx(30.0)


def test_delta_percent_none_when_zero_or_missing() -> None:
    assert (
        delta_percent(
            TrendVelocity(
                trend_id=1,
                metric="price",
                subject="aave",
                first_value=0.0,
                last_value=5.0,
            )
        )
        is None
    )
    assert (
        delta_percent(TrendVelocity(trend_id=1, metric="price", subject="aave")) is None
    )
