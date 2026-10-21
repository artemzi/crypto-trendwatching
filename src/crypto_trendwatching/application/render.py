"""Рендерер полного дайджеста §9 (M3): 8 секций с интерпретацией, whale и календарём."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from crypto_trendwatching.agent.loop import ResearchResult
from crypto_trendwatching.application.catalog import SourceRef
from crypto_trendwatching.application.freshness import delta_percent
from crypto_trendwatching.application.interpret import DISCLAIMER
from crypto_trendwatching.application.verify import CandidateVerdict
from crypto_trendwatching.domain.models import (
    Catalyst,
    Interpretation,
    ReportedTrend,
    Signal,
    TrendVelocity,
    WhaleTransfer,
    Zone,
)

_CONFIRMATION_CHANGE = 10.0


@dataclass(frozen=True)
class ReportContext:
    """Все данные, нужные рендереру дайджеста."""

    zone: Zone
    verdicts: list[CandidateVerdict]
    research: dict[int, ResearchResult]
    catalog: dict[str, SourceRef]
    funnel: dict[str, Any]
    interpretations: dict[int, Interpretation] = field(default_factory=dict)
    whale_verdicts: dict[int, str | None] = field(default_factory=dict)
    whale_transfers: list[WhaleTransfer] = field(default_factory=list)
    catalysts: list[Catalyst] = field(default_factory=list)
    weak_signals: list[Signal] = field(default_factory=list)
    fresh_trends: list[tuple[ReportedTrend, list[TrendVelocity]]] = field(
        default_factory=list
    )


def render_report(ctx: ReportContext) -> str:
    """Собрать Markdown-дайджест из 8 секций §9 требований."""
    passed = [v for v in ctx.verdicts if v.passed]
    repeats = [v for v in ctx.verdicts if v.is_repeat]

    lines: list[str] = [f"# Дайджест: {ctx.zone.name}", ""]
    lines.extend(_render_summary(ctx.zone, passed))
    lines.extend(_render_trends(ctx, passed))
    lines.extend(_render_freshness(ctx.fresh_trends))
    lines.extend(_render_weak_signals(ctx.weak_signals))
    lines.extend(_render_whale(ctx.whale_transfers))
    lines.extend(_render_catalysts(ctx.catalysts))
    lines.extend(_render_sources(ctx.catalog))
    lines.extend(_render_artifacts(ctx, repeats))
    lines.extend(["---", "", f"*{DISCLAIMER}*", ""])
    return "\n".join(lines)


def _render_summary(zone: Zone, passed: list[CandidateVerdict]) -> list[str]:
    lines = ["## Резюме недели"]
    top = ", ".join(v.candidate.name for v in passed[:3]) or "нет выраженных сдвигов"
    lines.append(f"Зона «{zone.name}»: ключевые сдвиги — {top}.")
    lines.append("")
    return lines


def _render_trends(ctx: ReportContext, passed: list[CandidateVerdict]) -> list[str]:
    lines = ["## Тренды"]
    if not passed:
        lines.extend(["", "_Трендов нет._", ""])
        return lines
    for verdict in passed:
        lines.extend(_render_trend(ctx, verdict))
    return lines


def _render_trend(ctx: ReportContext, verdict: CandidateVerdict) -> list[str]:
    candidate = verdict.candidate
    lines = ["", f"### {candidate.name}"]
    if candidate.maturity:
        lines.append(f"- Зрелость: {candidate.maturity}")
    if candidate.definition:
        lines.append(f"- {candidate.definition}")
    citations = ", ".join(f"[Ист]({n})" for n in sorted(candidate.catalog_numbers))
    if citations:
        lines.append(f"- Источники: {citations}")
    lines.append(f"- {_onchain_summary(ctx.research.get(candidate.id or 0))}")
    whale = ctx.whale_verdicts.get(candidate.id or 0)
    if whale:
        lines.append(f"- Whale-активность: {whale}")
    if verdict.pump:
        lines.append("- ⚠ Нарратив без on-chain-подтверждения (pump-фильтр)")
    if verdict.live_evidence == 0:
        lines.append("- Живых ссылок не найдено")
    lines.extend(_render_evidence(verdict))
    lines.extend(_render_interpretation(ctx.interpretations.get(candidate.id or 0)))
    return lines


def _render_interpretation(interpretation: Interpretation | None) -> list[str]:
    lines = ["- Интерпретация:"]
    if interpretation is None:
        lines.append("  - нет данных")
        return lines
    if interpretation.direction:
        lines.append(f"  - Направление нарратива: {interpretation.direction}")
    if interpretation.horizon:
        lines.append(f"  - Горизонт: {interpretation.horizon}")
    if interpretation.onchain_status:
        lines.append(f"  - On-chain: {interpretation.onchain_status}")
    if interpretation.catalysts:
        lines.append("  - Катализаторы: " + "; ".join(interpretation.catalysts))
    if interpretation.risk_flags:
        lines.append("  - Риски: " + "; ".join(interpretation.risk_flags))
    if interpretation.disclaimer:
        lines.append(f"  - {interpretation.disclaimer}")
    return lines


def _render_evidence(verdict: CandidateVerdict) -> list[str]:
    lines = ["- Доказательства:"]
    if not verdict.bindings:
        lines.append("  - нет собранных доказательств")
        return lines
    for binding in verdict.bindings:
        citation = (
            f" [Ист]({binding.catalog_number})"
            if binding.catalog_number is not None
            else ""
        )
        lines.append(f"  - «{binding.quote or ''}» — {binding.source_url}{citation}")
    return lines


def _render_freshness(
    fresh_trends: list[tuple[ReportedTrend, list[TrendVelocity]]],
) -> list[str]:
    lines = ["", "## Развитие ранее замеченных трендов"]
    if not fresh_trends:
        lines.extend(["", "_Ранее замеченных трендов нет._", ""])
        return lines
    for trend, velocities in fresh_trends:
        lines.append(f"- «{trend.name}»:")
        for velocity in velocities:
            delta = delta_percent(velocity)
            suffix = f" (Δ {delta:+.1f}%)" if delta is not None else ""
            lines.append(
                f"  - {velocity.metric} {velocity.subject}: "
                f"{velocity.first_value:,.0f} → {velocity.last_value:,.0f}{suffix}"
            )
    lines.append("")
    return lines


def _render_weak_signals(weak_signals: list[Signal]) -> list[str]:
    lines = ["", "## Слабые сигналы / зарождающиеся"]
    if not weak_signals:
        lines.extend(["", "_Слабых сигналов нет._", ""])
        return lines
    for signal in weak_signals[:20]:
        lines.append(f"- {signal.title or ''} — {signal.url}")
    lines.append("")
    return lines


def _render_whale(transfers: list[WhaleTransfer]) -> list[str]:
    lines = ["", "## Whale-активность недели"]
    if not transfers:
        lines.extend(["", "_Крупных трансферов нет._", ""])
        return lines
    for transfer in transfers[:20]:
        lines.append(
            f"- {transfer.asset or '?'}: ${transfer.amount_usd:,.0f} "
            f"({transfer.timestamp or ''})"
        )
    lines.append("")
    return lines


def _render_catalysts(catalysts: list[Catalyst]) -> list[str]:
    lines = ["", "## Катализаторы следующей недели"]
    if not catalysts:
        lines.extend(["", "_Катализаторов не найдено._", ""])
        return lines
    for catalyst in sorted(catalysts, key=lambda c: c.event_date or ""):
        date = f" ({catalyst.event_date})" if catalyst.event_date else ""
        category = f" [{catalyst.category}]" if catalyst.category else ""
        lines.append(f"- {catalyst.title}{date}{category}")
    lines.append("")
    return lines


def _onchain_summary(result: ResearchResult | None) -> str:
    observations = result.onchain if result is not None else []
    if not observations:
        return "On-chain: нет данных"
    parts = []
    confirmed = False
    for observation in observations:
        label = _metric_label(observation.metric)
        value = f"{observation.value:,.0f}" if observation.value is not None else "—"
        change = (
            f" (7д {observation.change_7d:+.1f}%)"
            if observation.change_7d is not None
            else ""
        )
        parts.append(f"{label} {observation.subject}: {value}{change}")
        if (
            observation.metric in {"tvl", "volume"}
            and observation.change_7d is not None
        ):
            confirmed = confirmed or observation.change_7d >= _CONFIRMATION_CHANGE
    status = "подтверждено деньгами" if confirmed else "не подтверждено деньгами"
    return f"On-chain [{status}]: " + "; ".join(parts)


def _metric_label(metric: str) -> str:
    return {"tvl": "TVL", "volume": "объём", "price": "цена"}.get(metric, metric)


def _render_sources(catalog: dict[str, SourceRef]) -> list[str]:
    lines = ["", "## Источники"]
    for ref in sorted(catalog.values(), key=lambda item: item.number):
        lines.append(f"{ref.number}. {ref.name} — {ref.url}")
    lines.append("")
    return lines


def _render_artifacts(ctx: ReportContext, repeats: list[CandidateVerdict]) -> list[str]:
    lines = ["## Отклонённые повторы"]
    if repeats:
        for verdict in repeats:
            lines.append(
                f"- «{verdict.candidate.name}» — ранее замечено: "
                f"{verdict.repeat_of or '?'}"
            )
    else:
        lines.append("_Повторов нет._")
    lines.append("")
    lines.append("## Воронка")
    lines.append("```json")
    lines.append(json.dumps(ctx.funnel, ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    return lines
