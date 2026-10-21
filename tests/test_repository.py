"""Tests for the SQLite repository."""

from pathlib import Path

import numpy as np

from crypto_trendwatching.adapters.sqlite_repository import SqliteRepository
from crypto_trendwatching.domain.models import ReportRun, Signal


def test_signal_round_trip(tmp_path: Path) -> None:
    repo = SqliteRepository(tmp_path / "test.db")
    signal = Signal(
        url="https://example.com/a",
        source_id="s1",
        zone_id="z1",
        title="Title",
        summary="Summary",
        published_at="2026-10-20T00:00:00+00:00",
        extra={"key": "value"},
    )
    signal_id = repo.save_signal(signal)
    assert signal_id >= 1

    signals = repo.list_signals("z1")
    assert len(signals) == 1
    assert signals[0].url == signal.url
    assert signals[0].source_id == "s1"
    assert signals[0].extra == {"key": "value"}
    repo.close()


def test_embedding_round_trip(tmp_path: Path) -> None:
    repo = SqliteRepository(tmp_path / "test.db")
    embedding = np.arange(8, dtype=np.float16)
    signal_id = repo.save_signal(
        Signal(url="https://example.com/b", zone_id="z1"), embedding
    )
    restored = repo.get_embedding(signal_id)
    assert restored is not None
    assert np.array_equal(restored, embedding)
    repo.close()


def test_run_round_trip(tmp_path: Path) -> None:
    repo = SqliteRepository(tmp_path / "test.db")
    run_id = repo.save_run(ReportRun(status="running"))
    repo.update_run(run_id, status="completed", report_md="# отчёт")

    run = repo.get_run(run_id)
    assert run is not None
    assert run.status == "completed"
    assert run.report_md == "# отчёт"

    runs = repo.list_runs()
    assert len(runs) == 1
    assert runs[0].id == run_id
    repo.close()


def test_update_run_unknown_column_rejected(tmp_path: Path) -> None:
    repo = SqliteRepository(tmp_path / "test.db")
    run_id = repo.save_run(ReportRun(status="running"))
    try:
        repo.update_run(run_id, not_a_column="x")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for unknown column")
    repo.close()
