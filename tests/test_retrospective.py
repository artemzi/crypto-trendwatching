"""Tests for the retrospective false-positive check (pump vs trend)."""

from __future__ import annotations

from pathlib import Path

from crypto_trendwatching.adapters.sqlite_repository import SqliteRepository
from crypto_trendwatching.application.retrospective import (
    classify_reversal,
    render_retro_report,
    run_retrospective,
)
from crypto_trendwatching.domain.models import (
    EvidenceVerdict,
    OnChainObservation,
    TrendCandidate,
)


def test_classify_reversal_pump_vs_trend() -> None:
    assert classify_reversal(100.0, 90.0) == "памп"
    assert classify_reversal(100.0, 110.0) == "тренд"
    assert classify_reversal(100.0, 100.0) == "тренд"


def test_classify_reversal_missing_data() -> None:
    assert classify_reversal(None, 110.0) == "недостаточно данных"
    assert classify_reversal(100.0, None) == "недостаточно данных"
    assert classify_reversal(0.0, 110.0) == "недостаточно данных"


def test_render_retro_report_empty() -> None:
    report = render_retro_report([])
    assert "Нет трендов" in report


class _FakeOnChain:
    def tvl(self, _protocol: str) -> float:
        return 0.0

    def volume(self, _protocol: str, _window: str) -> float:
        return 0.0

    def price(self, coin: str) -> float:
        del coin
        return 90.0

    def change(self, _metric: str, _subject: str, _window_days: int) -> float | None:
        return None


def test_run_retrospective_classifies_pump(tmp_path: Path) -> None:
    repo = SqliteRepository(tmp_path / "test.db")
    candidate_id = repo.save_trend_candidate(
        TrendCandidate(run_id=1, name="памп-тренд")
    )
    repo.save_evidence_verdict(
        EvidenceVerdict(verdict="pump", candidate_id=candidate_id)
    )
    repo.save_onchain_observation(
        OnChainObservation(
            run_id=1,
            candidate_id=candidate_id,
            metric="price",
            subject="btc",
            value=100.0,
            observed_at="2026-10-21T00:00:00+00:00",
        )
    )

    verdicts = run_retrospective(repo, _FakeOnChain())

    assert len(verdicts) == 1
    assert verdicts[0].trend == "памп-тренд"
    assert verdicts[0].first_price == 100.0
    assert verdicts[0].current_price == 90.0
    assert verdicts[0].verdict == "памп"
    repo.close()
