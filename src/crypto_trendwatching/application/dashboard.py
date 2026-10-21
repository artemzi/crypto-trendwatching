"""Данные и графики для интерактивного дашборда (M6)."""

from __future__ import annotations

import json
from typing import Any

import plotly.graph_objects as go

from crypto_trendwatching.domain.models import (
    Catalyst,
    OnChainObservation,
    TrendCandidate,
    WhaleTransfer,
)

_FUNNEL_STAGES = (
    ("collect", "Сигналы"),
    ("filter", "После отбора"),
    ("synthesize", "Кандидаты"),
    ("verify", "Тренды"),
)


def funnel_stages(funnel_json: str | None) -> list[dict[str, Any]]:
    """Упорядоченные этапы воронки (сигналы → отбор → кандидаты → тренды)."""
    if not funnel_json:
        return []
    try:
        data = json.loads(funnel_json)
    except json.JSONDecodeError:
        return []
    phases = data.get("phases") if isinstance(data, dict) else None
    if not isinstance(phases, dict):
        return []
    stages: list[dict[str, Any]] = []
    for stage, label in _FUNNEL_STAGES:
        phase = phases.get(stage) or {}
        if stage == "verify":
            count = phase.get("passed")
        elif stage == "filter":
            count = phase.get("signals")
        else:
            count = (
                phase.get("signals")
                if stage != "synthesize"
                else phase.get("candidates")
            )
        if isinstance(count, (int, float)):
            stages.append({"stage": stage, "label": label, "count": int(count)})
    return stages


def maturity_counts(candidates: list[TrendCandidate]) -> list[dict[str, Any]]:
    """Распределение кандидатов по зрелости."""
    counter: dict[str, int] = {}
    for candidate in candidates:
        maturity = candidate.maturity or "не указано"
        counter[maturity] = counter.get(maturity, 0) + 1
    return [{"name": name, "count": count} for name, count in counter.items()]


def onchain_items(observations: list[OnChainObservation]) -> list[dict[str, Any]]:
    """On-chain-снимки прогона."""
    return [
        {
            "metric": observation.metric,
            "subject": observation.subject,
            "value": observation.value,
            "change_7d": observation.change_7d,
            "change_30d": observation.change_30d,
        }
        for observation in observations
    ]


def whale_items(transfers: list[WhaleTransfer]) -> list[dict[str, Any]]:
    """Суммарный объём whale-трансферов по активу."""
    totals: dict[str, float] = {}
    for transfer in transfers:
        asset = transfer.asset or "?"
        totals[asset] = totals.get(asset, 0.0) + transfer.amount_usd
    return [
        {"asset": asset, "amount_usd": round(total, 2)}
        for asset, total in sorted(
            totals.items(), key=lambda item: item[1], reverse=True
        )
    ]


def catalyst_items(catalysts: list[Catalyst]) -> list[dict[str, Any]]:
    """Катализаторы прогона (сортировка по дате)."""
    items = [
        {
            "title": catalyst.title,
            "event_date": catalyst.event_date,
            "category": catalyst.category,
        }
        for catalyst in catalysts
    ]
    return sorted(items, key=lambda item: item["event_date"] or "")


def funnel_figure(stages: list[dict[str, Any]]) -> go.Figure:
    return go.Figure(
        go.Funnel(
            y=[stage["label"] for stage in stages],
            x=[stage["count"] for stage in stages],
        )
    )


def maturity_figure(counts: list[dict[str, Any]]) -> go.Figure:
    return go.Figure(
        go.Bar(
            x=[item["name"] for item in counts],
            y=[item["count"] for item in counts],
        )
    )


def onchain_figure(items: list[dict[str, Any]]) -> go.Figure:
    subjects = [f"{item['metric']} {item['subject']}" for item in items]
    return go.Figure(
        go.Bar(
            x=subjects,
            y=[item["change_7d"] for item in items],
            name="Δ 7д, %",
        )
    )


def whale_figure(items: list[dict[str, Any]]) -> go.Figure:
    return go.Figure(
        go.Bar(
            x=[item["asset"] for item in items],
            y=[item["amount_usd"] for item in items],
        )
    )


def catalyst_figure(items: list[dict[str, Any]]) -> go.Figure:
    titles = [item["title"] for item in items]
    dates = [item["event_date"] or "" for item in items]
    return go.Figure(
        go.Scatter(
            x=dates,
            y=titles,
            mode="markers+text",
            text=dates,
            textposition="top center",
        )
    )
