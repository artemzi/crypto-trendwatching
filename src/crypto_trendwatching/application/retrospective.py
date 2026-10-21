"""Ретроспективный false-positive: памп vs тренд для pump-флагов (D-08, D-26)."""

from __future__ import annotations

from dataclasses import dataclass

from crypto_trendwatching.domain.models import OnChainObservation, TrendCandidate
from crypto_trendwatching.domain.ports import OnChainClient, TrendRepository

_VERDICT_PUMP = "памп"
_VERDICT_TREND = "тренд"
_VERDICT_UNKNOWN = "недостаточно данных"


@dataclass(frozen=True)
class RetroVerdict:
    """Итог ретроспективной проверки одного pump-флага."""

    trend: str
    verdict: str
    first_price: float | None = None
    current_price: float | None = None


def classify_reversal(first_price: float | None, current_price: float | None) -> str:
    """Классификация через 2–4 недели: цена вернулась → памп, иначе тренд."""
    if first_price is None or current_price is None or first_price <= 0:
        return _VERDICT_UNKNOWN
    if current_price >= first_price:
        return _VERDICT_TREND
    return _VERDICT_PUMP


def run_retrospective(
    repository: TrendRepository, onchain: OnChainClient
) -> list[RetroVerdict]:
    """Проверить pump-флаги: сопоставить первую и текущую цену."""
    verdicts: list[RetroVerdict] = []
    for candidate in repository.list_pump_flagged_candidates():
        first_price = _first_price(
            repository.list_onchain_observations(candidate.id or 0)
        )
        current_price = _current_price(onchain, candidate, repository)
        verdicts.append(
            RetroVerdict(
                trend=candidate.name,
                verdict=classify_reversal(first_price, current_price),
                first_price=first_price,
                current_price=current_price,
            )
        )
    return verdicts


def render_retro_report(verdicts: list[RetroVerdict]) -> str:
    lines = ["# Ретроспективная проверка pump-флагов", ""]
    if not verdicts:
        lines.append("_Нет трендов с pump-флагом для проверки._")
        lines.append("")
        return "\n".join(lines)
    lines.append("| Тренд | Первая цена | Текущая цена | Вердикт |")
    lines.append("|---|---|---|---|")
    for verdict in verdicts:
        first = (
            f"{verdict.first_price:,.2f}" if verdict.first_price is not None else "—"
        )
        current = (
            f"{verdict.current_price:,.2f}"
            if verdict.current_price is not None
            else "—"
        )
        lines.append(f"| {verdict.trend} | {first} | {current} | {verdict.verdict} |")
    lines.append("")
    return "\n".join(lines)


def _first_price(observations: list[OnChainObservation]) -> float | None:
    for observation in observations:
        if observation.metric == "price" and observation.value is not None:
            return observation.value
    return None


def _current_price(
    onchain: OnChainClient,
    candidate: TrendCandidate,
    repository: TrendRepository,
) -> float | None:
    observations = repository.list_onchain_observations(candidate.id or 0)
    for observation in observations:
        if observation.metric == "price":
            return onchain.price(observation.subject)
    return None
