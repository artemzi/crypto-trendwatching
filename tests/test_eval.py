"""Tests for the eval metrics (precision/recall) and golden set loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from crypto_trendwatching.application.eval import (
    EvalMetrics,
    compute_metrics,
    load_golden_set,
    render_metrics_report,
)


def test_load_golden_set(tmp_path: Path) -> None:
    path = tmp_path / "golden.yaml"
    path.write_text(
        """
version: 1
zones:
  - zone_id: ai_crypto
    items:
      - { title: "сигнал 1", expected_trend: "AI-агенты" }
      - { title: "сигнал 2", expected_trend: null }
  - zone_id: defi
    expected_trends:
      - "DeFi-хранилища"
      - "Рестейкинг"
""",
        encoding="utf-8",
    )

    zones = load_golden_set(path)

    assert len(zones) == 2
    assert zones[0].zone_id == "ai_crypto"
    assert zones[0].items[0].expected_trend == "AI-агенты"
    assert zones[0].items[1].expected_trend is None
    assert zones[1].expected() == {"DeFi-хранилища", "Рестейкинг"}


def test_compute_metrics_perfect() -> None:
    metrics = compute_metrics({"Тренд A", "Тренд B"}, {"Тренд A", "Тренд B"})
    assert metrics.precision == pytest.approx(1.0)
    assert metrics.recall == pytest.approx(1.0)
    assert metrics.f1 == pytest.approx(1.0)


def test_compute_metrics_partial() -> None:
    metrics = compute_metrics({"Тренд A"}, {"Тренд A", "Тренд B"})
    assert metrics.precision == pytest.approx(1.0)
    assert metrics.recall == pytest.approx(0.5)


def test_compute_metrics_empty_expected() -> None:
    metrics = compute_metrics({"Тренд A"}, set())
    assert metrics.precision == pytest.approx(0.0)
    assert metrics.recall == pytest.approx(1.0)


def test_compute_metrics_case_insensitive() -> None:
    metrics = compute_metrics({"тренд a"}, {"Тренд A"})
    assert metrics.precision == pytest.approx(1.0)


def test_render_metrics_report_has_table() -> None:
    report = render_metrics_report({"defi": EvalMetrics(0.8, 0.6, 0.686)})
    assert "| defi |" in report
    assert "Precision" in report
