"""Tests for the verification chain (liveness / anti-repeat / pump)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from crypto_trendwatching.adapters.sqlite_repository import SqliteRepository
from crypto_trendwatching.adapters.stubs import StubEmbedder
from crypto_trendwatching.agent.loop import ResearchResult
from crypto_trendwatching.application.verify import Verifier
from crypto_trendwatching.domain.models import (
    AgentTurn,
    EvidenceBinding,
    OnChainObservation,
    ReportedTrend,
    TrendCandidate,
)


class VerdictLlm:
    def __init__(self, verdict: str = "sound") -> None:
        self._verdict = verdict

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Any = None,
        max_tokens: int | None = None,
    ) -> str:
        del messages, tools, max_tokens
        return json.dumps({"verdict": self._verdict, "reason": "ok"})

    def complete_with_tools(
        self, messages: list[dict[str, Any]], tools: Any = None
    ) -> AgentTurn:
        del messages, tools
        return AgentTurn(content="")


def _save_candidate(
    repo: SqliteRepository, run_id: int, name: str, definition: str = ""
) -> TrendCandidate:
    candidate_id = repo.save_trend_candidate(
        TrendCandidate(run_id=run_id, name=name, definition=definition)
    )
    return TrendCandidate(
        run_id=run_id, name=name, definition=definition, id=candidate_id
    )


def _verifier(repo: SqliteRepository, liveness: Any) -> tuple[Verifier, StubEmbedder]:
    embedder = StubEmbedder()
    return Verifier(repo, embedder, VerdictLlm(), liveness=liveness), embedder


def test_liveness_marks_dead_url(tmp_path: Path) -> None:
    repo = SqliteRepository(tmp_path / "test.db")
    verifier, _ = _verifier(repo, liveness=lambda _url: False)
    candidate = _save_candidate(repo, 1, "Тренд")
    research = {
        candidate.id or 0: ResearchResult(
            notes="",
            evidence=[
                EvidenceBinding(source_url="https://dead.example.com/x", quote="q")
            ],
        )
    }

    verdicts = verifier.verify_candidates([candidate], research)

    assert verdicts[0].passed is True
    assert verdicts[0].live_evidence == 0
    assert any(v.verdict == "dead" for v in verdicts[0].verdicts)
    repo.close()


def test_liveness_counts_live_url(tmp_path: Path) -> None:
    repo = SqliteRepository(tmp_path / "test.db")
    verifier, _ = _verifier(repo, liveness=lambda _url: True)
    candidate = _save_candidate(repo, 1, "Тренд")
    research = {
        candidate.id or 0: ResearchResult(
            notes="",
            evidence=[
                EvidenceBinding(source_url="https://live.example.com/x", quote="q")
            ],
        )
    }

    verdicts = verifier.verify_candidates([candidate], research)

    assert verdicts[0].live_evidence == 1
    assert any(v.verdict == "live" for v in verdicts[0].verdicts)
    repo.close()


def test_anti_repeat_rejects_duplicate(tmp_path: Path) -> None:
    repo = SqliteRepository(tmp_path / "test.db")
    verifier, embedder = _verifier(repo, liveness=lambda _url: True)
    repo.save_reported_trend(
        ReportedTrend(
            name="ранее замеченный",
            definition="x",
            embedding=embedder.embed(["дубль тренда"])[0],
        )
    )
    candidate = _save_candidate(repo, 1, "дубль тренда")

    verdicts = verifier.verify_candidates([candidate], {})

    assert verdicts[0].passed is False
    assert verdicts[0].is_repeat is True
    assert verdicts[0].repeat_of == "ранее замеченный"
    repo.close()


def test_pump_flag_when_price_rises_without_tvl(tmp_path: Path) -> None:
    repo = SqliteRepository(tmp_path / "test.db")
    verifier, _ = _verifier(repo, liveness=lambda _url: True)
    candidate = _save_candidate(repo, 1, "памп-тренд")
    research = {
        candidate.id or 0: ResearchResult(
            notes="",
            onchain=[
                OnChainObservation(
                    run_id=1, metric="price", subject="x", change_7d=35.0
                )
            ],
        )
    }

    verdicts = verifier.verify_candidates([candidate], research)

    assert verdicts[0].pump is True
    assert verdicts[0].passed is True
    assert any(v.verdict == "pump" for v in verdicts[0].verdicts)
    repo.close()


def test_no_pump_when_tvl_confirms(tmp_path: Path) -> None:
    repo = SqliteRepository(tmp_path / "test.db")
    verifier, _ = _verifier(repo, liveness=lambda _url: True)
    candidate = _save_candidate(repo, 1, "подтверждённый тренд")
    research = {
        candidate.id or 0: ResearchResult(
            notes="",
            onchain=[
                OnChainObservation(
                    run_id=1, metric="price", subject="x", change_7d=35.0
                ),
                OnChainObservation(run_id=1, metric="tvl", subject="x", change_7d=15.0),
            ],
        )
    }

    verdicts = verifier.verify_candidates([candidate], research)

    assert verdicts[0].pump is False
    repo.close()
