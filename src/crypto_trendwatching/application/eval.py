"""Eval-набор и метрики качества (precision/recall) против золотого сета."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class GoldenItem:
    """Один размеченный сигнал: заголовок → ожидаемый тренд (или None = не-тренд)."""

    title: str
    expected_trend: str | None = None


@dataclass(frozen=True)
class GoldenZone:
    """Золотой сет по одной зоне: сигнальные метки и/или ожидаемые имена трендов."""

    zone_id: str
    items: list[GoldenItem] = field(default_factory=list)
    expected_trends: list[str] = field(default_factory=list)

    def expected(self) -> set[str]:
        """Множество ожидаемых имён трендов (из обоих представлений)."""
        from_items = {item.expected_trend for item in self.items if item.expected_trend}
        return set(self.expected_trends) | from_items


@dataclass(frozen=True)
class EvalMetrics:
    """Метрики качества на одной зоне."""

    precision: float
    recall: float
    f1: float


def load_golden_set(path: Path) -> list[GoldenZone]:
    """Загрузить золотой сет из ``data/eval/*.yaml``."""
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        return []
    zones: list[GoldenZone] = []
    for entry in data.get("zones", []):
        if not isinstance(entry, dict) or "zone_id" not in entry:
            continue
        items = [
            GoldenItem(
                title=str(item["title"]),
                expected_trend=item.get("expected_trend"),
            )
            for item in entry.get("items", [])
            if isinstance(item, dict) and "title" in item
        ]
        expected_trends = [
            str(trend)
            for trend in entry.get("expected_trends", [])
            if isinstance(trend, str)
        ]
        zones.append(
            GoldenZone(
                zone_id=str(entry["zone_id"]),
                items=items,
                expected_trends=expected_trends,
            )
        )
    return zones


def compute_metrics(predicted: set[str], expected: set[str]) -> EvalMetrics:
    """Precision/recall/F1 по совпадению имён трендов (регистронезависимо)."""
    predicted_norm = {_norm(name) for name in predicted if name}
    expected_norm = {_norm(name) for name in expected if name}
    true_positive = len(predicted_norm & expected_norm)
    precision = true_positive / len(predicted_norm) if predicted_norm else 0.0
    recall = true_positive / len(expected_norm) if expected_norm else 1.0
    f1 = (
        2 * precision * recall / (precision + recall) if precision + recall > 0 else 0.0
    )
    return EvalMetrics(precision=precision, recall=recall, f1=f1)


def render_metrics_report(per_zone: dict[str, EvalMetrics]) -> str:
    """Markdown-отчёт метрик по зонам."""
    lines = ["# Метрики качества (eval)", ""]
    lines.append("| Зона | Precision | Recall | F1 |")
    lines.append("|---|---|---|---|")
    for zone_id, metrics in sorted(per_zone.items()):
        lines.append(
            f"| {zone_id} | {metrics.precision:.2f} | {metrics.recall:.2f} | "
            f"{metrics.f1:.2f} |"
        )
    lines.append("")
    return "\n".join(lines)


def _norm(name: str) -> str:
    return name.strip().lower()
