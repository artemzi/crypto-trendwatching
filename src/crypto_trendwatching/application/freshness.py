"""Freshness-декей (FR-11): снимки цены/TVL ранее замеченных трендов."""

from __future__ import annotations

from crypto_trendwatching.application.config_loader import OnChainMapping
from crypto_trendwatching.domain.models import TrendVelocity
from crypto_trendwatching.domain.ports import OnChainClient, TrendRepository


def measure_velocity(
    repository: TrendRepository,
    onchain: OnChainClient,
    trend_id: int,
    mapping: OnChainMapping | None,
    measured_at: str,
) -> list[TrendVelocity]:
    """Записать/обновить снимок цены и TVL для тренда (upsert в trend_velocity)."""
    results: list[TrendVelocity] = []
    if mapping is None:
        return results
    if mapping.coins:
        subject = mapping.coins[0]
        value = onchain.price(subject)
        if value > 0:
            results.append(
                repository.upsert_trend_velocity(
                    trend_id, "price", subject, value, measured_at
                )
            )
    if mapping.protocols:
        subject = mapping.protocols[0]
        value = onchain.tvl(subject)
        if value > 0:
            results.append(
                repository.upsert_trend_velocity(
                    trend_id, "tvl", subject, value, measured_at
                )
            )
    return results


def delta_percent(velocity: TrendVelocity) -> float | None:
    """Процентное изменение first_value → last_value (None при нехватке данных)."""
    first = velocity.first_value
    last = velocity.last_value
    if first is None or last is None or first == 0.0:
        return None
    return (last - first) / first * 100.0
