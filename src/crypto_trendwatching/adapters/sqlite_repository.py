"""SQLite-репозиторий (WAL), реализующий TrendRepository."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np

from crypto_trendwatching.domain.models import (
    Catalyst,
    EvidenceBinding,
    EvidenceVerdict,
    OnChainObservation,
    ReportedTrend,
    ReportRun,
    Signal,
    TrendCandidate,
    TrendVelocity,
    WhaleTransfer,
)
from crypto_trendwatching.domain.ports import Embedding

_SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS trend_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  zone_id TEXT NOT NULL,
  source_id TEXT,
  url TEXT NOT NULL,
  title TEXT,
  summary TEXT,
  published_at TEXT,
  embedding BLOB,
  extra_json TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_trend_items_zone ON trend_items(zone_id);

CREATE TABLE IF NOT EXISTS reported_trends (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  definition TEXT,
  maturity TEXT,
  embedding BLOB,
  first_reported_at TEXT,
  last_reported_at TEXT
);

CREATE TABLE IF NOT EXISTS trend_candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  definition TEXT,
  maturity TEXT,
  catalog_numbers TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS evidence_bindings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  candidate_id INTEGER,
  source_url TEXT NOT NULL,
  quote TEXT,
  catalog_number INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS evidence_verdicts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  binding_id INTEGER,
  candidate_id INTEGER,
  verdict TEXT NOT NULL,
  reason TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS onchain_observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  candidate_id INTEGER,
  metric TEXT NOT NULL,
  subject TEXT NOT NULL,
  value REAL,
  change_7d REAL,
  change_30d REAL,
  observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_onchain_observations_run ON onchain_observations(run_id);

CREATE TABLE IF NOT EXISTS whale_transfers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  amount_usd REAL NOT NULL,
  asset TEXT,
  from_address TEXT,
  to_address TEXT,
  timestamp TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_whale_transfers_run ON whale_transfers(run_id);

CREATE TABLE IF NOT EXISTS catalysts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  candidate_id INTEGER,
  event_date TEXT,
  title TEXT NOT NULL,
  category TEXT,
  source_url TEXT
);
CREATE INDEX IF NOT EXISTS idx_catalysts_run ON catalysts(run_id);

CREATE TABLE IF NOT EXISTS trend_velocity (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trend_id INTEGER NOT NULL,
  metric TEXT NOT NULL,
  subject TEXT NOT NULL,
  first_value REAL,
  last_value REAL,
  measured_at TEXT NOT NULL,
  UNIQUE(trend_id, metric, subject)
);

CREATE TABLE IF NOT EXISTS zone_run_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  zone_id TEXT NOT NULL,
  status TEXT NOT NULL,
  checkpoint_json TEXT,
  started_at TEXT,
  finished_at TEXT
);

CREATE TABLE IF NOT EXISTS search_ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  provider TEXT NOT NULL,
  query TEXT NOT NULL,
  results_count INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS report_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  status TEXT NOT NULL,
  zone_id TEXT,
  funnel_json TEXT,
  report_md TEXT,
  report_docx BLOB,
  started_at TEXT,
  finished_at TEXT,
  error TEXT
);
"""

_RUN_COLUMNS = {
    "status",
    "zone_id",
    "funnel_json",
    "report_md",
    "report_docx",
    "started_at",
    "finished_at",
    "error",
}


class SqliteRepository:
    """SQLite-backed TrendRepository."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._migrate()

    def close(self) -> None:
        self._conn.close()

    def _migrate(self) -> None:
        """Инкрементальные миграции схемы (M2 evidence_verdicts, M4 report_runs.error)."""
        self._migrate_evidence_verdicts()
        self._migrate_report_runs_error()

    def _migrate_evidence_verdicts(self) -> None:
        columns = {
            row["name"]
            for row in self._conn.execute(
                "PRAGMA table_info(evidence_verdicts)"
            ).fetchall()
        }
        if "candidate_id" in columns:
            return
        self._conn.execute(
            "ALTER TABLE evidence_verdicts RENAME TO evidence_verdicts_old"
        )
        self._conn.execute(
            """
            CREATE TABLE evidence_verdicts (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              binding_id INTEGER,
              candidate_id INTEGER,
              verdict TEXT NOT NULL,
              reason TEXT,
              created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        self._conn.execute(
            "INSERT INTO evidence_verdicts (id, binding_id, verdict, reason, created_at) "
            "SELECT id, binding_id, verdict, reason, created_at FROM evidence_verdicts_old"
        )
        self._conn.execute("DROP TABLE evidence_verdicts_old")
        self._conn.commit()

    def _migrate_report_runs_error(self) -> None:
        columns = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(report_runs)").fetchall()
        }
        for column in ("zone_id", "error"):
            if column not in columns:
                self._conn.execute(f"ALTER TABLE report_runs ADD COLUMN {column} TEXT")
        self._conn.commit()

    def save_signal(self, s: Signal, embedding: Embedding | None = None) -> int:
        cursor = self._conn.execute(
            "INSERT INTO trend_items "
            "(zone_id, source_id, url, title, summary, published_at, embedding, extra_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                s.zone_id,
                s.source_id,
                s.url,
                s.title,
                s.summary,
                s.published_at,
                _embedding_to_blob(embedding),
                json.dumps(s.extra, ensure_ascii=False) if s.extra else None,
            ),
        )
        self._conn.commit()
        return _last_row_id(cursor)

    def list_signals(self, zone_id: str) -> list[Signal]:
        rows = self._conn.execute(
            "SELECT * FROM trend_items WHERE zone_id = ? ORDER BY id", (zone_id,)
        ).fetchall()
        return [_row_to_signal(row) for row in rows]

    def get_embedding(self, signal_id: int) -> Embedding | None:
        row = self._conn.execute(
            "SELECT embedding FROM trend_items WHERE id = ?", (signal_id,)
        ).fetchone()
        if row is None:
            return None
        return _blob_to_embedding(row["embedding"])

    def save_reported_trend(self, t: ReportedTrend) -> int:
        cursor = self._conn.execute(
            "INSERT INTO reported_trends "
            "(name, definition, maturity, embedding, first_reported_at, last_reported_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                t.name,
                t.definition,
                t.maturity,
                _embedding_to_blob(t.embedding),
                t.first_reported_at,
                t.last_reported_at,
            ),
        )
        self._conn.commit()
        return _last_row_id(cursor)

    def list_reported_trends(self) -> list[ReportedTrend]:
        rows = self._conn.execute(
            "SELECT * FROM reported_trends ORDER BY id"
        ).fetchall()
        return [_row_to_reported_trend(row) for row in rows]

    def save_trend_candidate(self, candidate: TrendCandidate) -> int:
        cursor = self._conn.execute(
            "INSERT INTO trend_candidates "
            "(run_id, name, definition, maturity, catalog_numbers) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                candidate.run_id,
                candidate.name,
                candidate.definition,
                candidate.maturity,
                json.dumps(candidate.catalog_numbers),
            ),
        )
        self._conn.commit()
        return _last_row_id(cursor)

    def list_trend_candidates(self, run_id: int) -> list[TrendCandidate]:
        rows = self._conn.execute(
            "SELECT * FROM trend_candidates WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
        return [_row_to_candidate(row) for row in rows]

    def save_evidence_binding(self, binding: EvidenceBinding) -> int:
        cursor = self._conn.execute(
            "INSERT INTO evidence_bindings "
            "(candidate_id, source_url, quote, catalog_number) VALUES (?, ?, ?, ?)",
            (
                binding.candidate_id,
                binding.source_url,
                binding.quote,
                binding.catalog_number,
            ),
        )
        self._conn.commit()
        return _last_row_id(cursor)

    def list_evidence_bindings(self, candidate_id: int) -> list[EvidenceBinding]:
        rows = self._conn.execute(
            "SELECT * FROM evidence_bindings WHERE candidate_id = ? ORDER BY id",
            (candidate_id,),
        ).fetchall()
        return [_row_to_evidence_binding(row) for row in rows]

    def save_evidence_verdict(self, verdict: EvidenceVerdict) -> int:
        cursor = self._conn.execute(
            "INSERT INTO evidence_verdicts "
            "(binding_id, candidate_id, verdict, reason) VALUES (?, ?, ?, ?)",
            (
                verdict.binding_id,
                verdict.candidate_id,
                verdict.verdict,
                verdict.reason,
            ),
        )
        self._conn.commit()
        return _last_row_id(cursor)

    def list_evidence_verdicts(self, candidate_id: int) -> list[EvidenceVerdict]:
        rows = self._conn.execute(
            "SELECT * FROM evidence_verdicts WHERE candidate_id = ? ORDER BY id",
            (candidate_id,),
        ).fetchall()
        return [_row_to_evidence_verdict(row) for row in rows]

    def save_onchain_observation(self, observation: OnChainObservation) -> int:
        cursor = self._conn.execute(
            "INSERT INTO onchain_observations "
            "(run_id, candidate_id, metric, subject, value, change_7d, change_30d, observed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                observation.run_id,
                observation.candidate_id,
                observation.metric,
                observation.subject,
                observation.value,
                observation.change_7d,
                observation.change_30d,
                observation.observed_at,
            ),
        )
        self._conn.commit()
        return _last_row_id(cursor)

    def list_onchain_observations(self, candidate_id: int) -> list[OnChainObservation]:
        rows = self._conn.execute(
            "SELECT * FROM onchain_observations WHERE candidate_id = ? ORDER BY id",
            (candidate_id,),
        ).fetchall()
        return [_row_to_onchain_observation(row) for row in rows]

    def list_onchain_observations_by_run(self, run_id: int) -> list[OnChainObservation]:
        rows = self._conn.execute(
            "SELECT * FROM onchain_observations WHERE run_id = ? ORDER BY id",
            (run_id,),
        ).fetchall()
        return [_row_to_onchain_observation(row) for row in rows]

    def list_pump_flagged_candidates(self) -> list[TrendCandidate]:
        rows = self._conn.execute(
            "SELECT DISTINCT tc.* FROM trend_candidates tc "
            "JOIN evidence_verdicts ev ON ev.candidate_id = tc.id "
            "WHERE ev.verdict = 'pump' ORDER BY tc.id"
        ).fetchall()
        return [_row_to_candidate(row) for row in rows]

    def save_whale_transfer(self, run_id: int, transfer: WhaleTransfer) -> int:
        cursor = self._conn.execute(
            "INSERT INTO whale_transfers "
            "(run_id, amount_usd, asset, from_address, to_address, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                run_id,
                transfer.amount_usd,
                transfer.asset,
                transfer.from_address,
                transfer.to_address,
                transfer.timestamp,
            ),
        )
        self._conn.commit()
        return _last_row_id(cursor)

    def list_whale_transfers(self, run_id: int) -> list[WhaleTransfer]:
        rows = self._conn.execute(
            "SELECT * FROM whale_transfers WHERE run_id = ? ORDER BY id", (run_id,)
        ).fetchall()
        return [_row_to_whale_transfer(row) for row in rows]

    def save_catalyst(self, catalyst: Catalyst) -> int:
        cursor = self._conn.execute(
            "INSERT INTO catalysts "
            "(run_id, candidate_id, event_date, title, category, source_url) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                catalyst.run_id,
                catalyst.candidate_id,
                catalyst.event_date,
                catalyst.title,
                catalyst.category,
                catalyst.source_url,
            ),
        )
        self._conn.commit()
        return _last_row_id(cursor)

    def list_catalysts(self, run_id: int) -> list[Catalyst]:
        rows = self._conn.execute(
            "SELECT * FROM catalysts WHERE run_id = ? ORDER BY event_date, id",
            (run_id,),
        ).fetchall()
        return [_row_to_catalyst(row) for row in rows]

    def upsert_trend_velocity(
        self,
        trend_id: int,
        metric: str,
        subject: str,
        value: float,
        measured_at: str,
    ) -> TrendVelocity:
        row = self._conn.execute(
            "SELECT * FROM trend_velocity WHERE trend_id = ? AND metric = ? AND subject = ?",
            (trend_id, metric, subject),
        ).fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO trend_velocity "
                "(trend_id, metric, subject, first_value, last_value, measured_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (trend_id, metric, subject, value, value, measured_at),
            )
        else:
            self._conn.execute(
                "UPDATE trend_velocity SET last_value = ?, measured_at = ? WHERE id = ?",
                (value, measured_at, row["id"]),
            )
        self._conn.commit()
        return TrendVelocity(
            trend_id=trend_id,
            metric=metric,
            subject=subject,
            first_value=row["first_value"] if row is not None else value,
            last_value=value,
            measured_at=measured_at,
        )

    def list_trend_velocity(self, trend_id: int) -> list[TrendVelocity]:
        rows = self._conn.execute(
            "SELECT * FROM trend_velocity WHERE trend_id = ? ORDER BY id", (trend_id,)
        ).fetchall()
        return [_row_to_trend_velocity(row) for row in rows]

    def save_run(self, run: ReportRun) -> int:
        cursor = self._conn.execute(
            "INSERT INTO report_runs "
            "(status, zone_id, funnel_json, report_md, report_docx, started_at, finished_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                run.status,
                run.zone_id,
                run.funnel_json,
                run.report_md,
                run.report_docx,
                run.started_at,
                run.finished_at,
            ),
        )
        self._conn.commit()
        return _last_row_id(cursor)

    def update_run(self, run_id: int, **kwargs: Any) -> None:
        if not kwargs:
            return
        assignments: list[str] = []
        values: list[Any] = []
        for column, value in kwargs.items():
            if column not in _RUN_COLUMNS:
                raise ValueError(f"неизвестная колонка report_runs: {column}")
            assignments.append(f"{column} = ?")
            values.append(value)
        values.append(run_id)
        sql = "UPDATE report_runs SET " + ", ".join(assignments) + " WHERE id = ?"  # noqa: S608  # nosec B608 — имена колонок из whitelist, значения параметризованы
        self._conn.execute(sql, values)
        self._conn.commit()

    def get_run(self, run_id: int) -> ReportRun | None:
        row = self._conn.execute(
            "SELECT * FROM report_runs WHERE id = ?", (run_id,)
        ).fetchone()
        return _row_to_run(row) if row is not None else None

    def list_runs(self) -> list[ReportRun]:
        rows = self._conn.execute(
            "SELECT * FROM report_runs ORDER BY id DESC"
        ).fetchall()
        return [_row_to_run(row) for row in rows]

    def delete_run(self, run_id: int) -> bool:
        """Удалить прогон и связанные данные (каскад по таблицам)."""
        candidate_ids = [
            row["id"]
            for row in self._conn.execute(
                "SELECT id FROM trend_candidates WHERE run_id = ?", (run_id,)
            ).fetchall()
        ]
        for candidate_id in candidate_ids:
            self._conn.execute(
                "DELETE FROM evidence_bindings WHERE candidate_id = ?", (candidate_id,)
            )
            self._conn.execute(
                "DELETE FROM evidence_verdicts WHERE candidate_id = ?", (candidate_id,)
            )
        for table in (
            "trend_candidates",
            "zone_run_results",
            "onchain_observations",
            "whale_transfers",
            "catalysts",
            "search_ledger",
        ):
            self._conn.execute(f"DELETE FROM {table} WHERE run_id = ?", (run_id,))  # noqa: S608  # nosec B608 — имена таблиц из фиксированного whitelist, run_id параметризован
        cursor = self._conn.execute("DELETE FROM report_runs WHERE id = ?", (run_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def save_zone_result(
        self,
        run_id: int,
        zone_id: str,
        status: str,
        checkpoint: dict[str, Any] | None = None,
    ) -> int:
        cursor = self._conn.execute(
            "INSERT INTO zone_run_results (run_id, zone_id, status, checkpoint_json) "
            "VALUES (?, ?, ?, ?)",
            (
                run_id,
                zone_id,
                status,
                json.dumps(checkpoint, ensure_ascii=False) if checkpoint else None,
            ),
        )
        self._conn.commit()
        return _last_row_id(cursor)


def _embedding_to_blob(embedding: Embedding | None) -> bytes | None:
    if embedding is None:
        return None
    return np.asarray(embedding, dtype=np.float16).tobytes()


def _last_row_id(cursor: sqlite3.Cursor) -> int:
    row_id = cursor.lastrowid
    if row_id is None:
        raise RuntimeError("ожидался lastrowid после INSERT")
    return row_id


def _blob_to_embedding(blob: bytes | None) -> Embedding | None:
    if blob is None:
        return None
    return np.frombuffer(blob, dtype=np.float16)


def _row_to_signal(row: sqlite3.Row) -> Signal:
    return Signal(
        url=row["url"],
        source_id=row["source_id"],
        zone_id=row["zone_id"],
        title=row["title"],
        summary=row["summary"],
        published_at=row["published_at"],
        extra=json.loads(row["extra_json"]) if row["extra_json"] else {},
    )


def _row_to_candidate(row: sqlite3.Row) -> TrendCandidate:
    return TrendCandidate(
        run_id=row["run_id"],
        name=row["name"],
        definition=row["definition"],
        maturity=row["maturity"],
        catalog_numbers=json.loads(row["catalog_numbers"])
        if row["catalog_numbers"]
        else [],
        id=row["id"],
    )


def _row_to_reported_trend(row: sqlite3.Row) -> ReportedTrend:
    return ReportedTrend(
        name=row["name"],
        definition=row["definition"],
        maturity=row["maturity"],
        embedding=_blob_to_embedding(row["embedding"]),
        first_reported_at=row["first_reported_at"],
        last_reported_at=row["last_reported_at"],
        id=row["id"],
    )


def _row_to_evidence_binding(row: sqlite3.Row) -> EvidenceBinding:
    return EvidenceBinding(
        source_url=row["source_url"],
        quote=row["quote"],
        catalog_number=row["catalog_number"],
        candidate_id=row["candidate_id"],
    )


def _row_to_evidence_verdict(row: sqlite3.Row) -> EvidenceVerdict:
    return EvidenceVerdict(
        verdict=row["verdict"],
        reason=row["reason"],
        binding_id=row["binding_id"],
        candidate_id=row["candidate_id"],
    )


def _row_to_whale_transfer(row: sqlite3.Row) -> WhaleTransfer:
    return WhaleTransfer(
        amount_usd=row["amount_usd"],
        asset=row["asset"],
        from_address=row["from_address"],
        to_address=row["to_address"],
        timestamp=row["timestamp"],
    )


def _row_to_onchain_observation(row: sqlite3.Row) -> OnChainObservation:
    return OnChainObservation(
        run_id=row["run_id"],
        metric=row["metric"],
        subject=row["subject"],
        value=row["value"],
        change_7d=row["change_7d"],
        change_30d=row["change_30d"],
        observed_at=row["observed_at"],
        candidate_id=row["candidate_id"],
    )


def _row_to_catalyst(row: sqlite3.Row) -> Catalyst:
    return Catalyst(
        run_id=row["run_id"],
        title=row["title"],
        event_date=row["event_date"],
        category=row["category"],
        candidate_id=row["candidate_id"],
        source_url=row["source_url"],
    )


def _row_to_trend_velocity(row: sqlite3.Row) -> TrendVelocity:
    return TrendVelocity(
        trend_id=row["trend_id"],
        metric=row["metric"],
        subject=row["subject"],
        first_value=row["first_value"],
        last_value=row["last_value"],
        measured_at=row["measured_at"],
    )


def _row_to_run(row: sqlite3.Row) -> ReportRun:
    return ReportRun(
        id=row["id"],
        status=row["status"],
        zone_id=row["zone_id"],
        funnel_json=row["funnel_json"],
        report_md=row["report_md"],
        report_docx=row["report_docx"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        error=row["error"],
    )
