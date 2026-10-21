"""Tests for the FastAPI web UI."""

import importlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from crypto_trendwatching.api.app import (
    _estimated_finish,
    _median_duration_seconds,
    create_app,
)
from crypto_trendwatching.config import settings
from crypto_trendwatching.domain.models import ReportRun
from crypto_trendwatching.domain.ports import TrendRepository


class _FakePipeline:
    def __init__(self, repository: TrendRepository) -> None:
        self._repository = repository

    def execute(self, run_id: int, zone: object) -> None:
        del zone
        self._repository.update_run(
            run_id, status="completed", finished_at="2026-10-21T00:00:00+00:00"
        )


@pytest.fixture
def client(
    tmp_path: Path, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setattr(settings, "config_dir", config_dir)
    monkeypatch.setattr(settings, "database_path", tmp_path / "api.db")
    application = create_app()
    with TestClient(application) as test_client:
        yield test_client


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_index(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Crypto Trendwatching" in response.text


def test_list_runs_empty(client: TestClient) -> None:
    response = client.get("/runs")
    assert response.status_code == 200
    assert response.json() == []


def test_get_run_missing(client: TestClient) -> None:
    response = client.get("/runs/9999")
    assert response.status_code == 404


def test_report_missing(client: TestClient) -> None:
    response = client.get("/report/9999")
    assert response.status_code == 404


def test_report_docx_missing(client: TestClient) -> None:
    response = client.get("/report/9999/docx")
    assert response.status_code == 404


def test_view_report_renders_html_and_download_link(client: TestClient) -> None:
    repository = cast(Any, client.app).state.repository
    run_id = repository.save_run(
        ReportRun(status="running", started_at="2026-10-21T00:00:00+00:00")
    )
    repository.update_run(
        run_id,
        status="completed",
        report_md="# Заголовок\n\n## Тренды\n\n- пункт",
        report_docx=b"PK\x03\x04",
    )

    response = client.get(f"/runs/{run_id}/report")
    assert response.status_code == 200
    assert "<h1>Заголовок</h1>" in response.text
    assert "Скачать DOCX" in response.text

    docx = client.get(f"/report/{run_id}/docx")
    assert docx.status_code == 200
    assert docx.content[:2] == b"PK"


def test_start_run_unknown_zone(client: TestClient) -> None:
    response = client.post("/runs", json={"zone_id": "no_such_zone"})
    assert response.status_code == 404


def test_delete_run(client: TestClient) -> None:
    repository = cast(Any, client.app).state.repository
    run_id = repository.save_run(ReportRun(status="running"))
    response = client.delete(f"/runs/{run_id}")
    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    assert repository.get_run(run_id) is None


def test_delete_run_missing(client: TestClient) -> None:
    response = client.delete("/runs/9999")
    assert response.status_code == 404


def test_median_duration_seconds() -> None:
    assert _median_duration_seconds([]) is None
    runs = [
        ReportRun(
            status="completed",
            started_at="2026-10-21T00:00:00+00:00",
            finished_at="2026-10-21T00:00:10+00:00",
        ),
        ReportRun(
            status="completed",
            started_at="2026-10-21T00:00:00+00:00",
            finished_at="2026-10-21T00:00:20+00:00",
        ),
        ReportRun(
            status="completed",
            started_at="2026-10-21T00:00:00+00:00",
            finished_at="2026-10-21T00:00:30+00:00",
        ),
        ReportRun(status="running", started_at="2026-10-21T00:00:00+00:00"),
    ]
    assert _median_duration_seconds(runs) == 20.0


def test_estimated_finish() -> None:
    run = ReportRun(status="running", started_at="2026-10-21T00:00:00+00:00")
    assert _estimated_finish(run, None) == ""
    estimated = _estimated_finish(run, 60.0)
    assert "/" in estimated  # формат D/M/Y H:M:S
    completed = ReportRun(status="completed", started_at="2026-10-21T00:00:00+00:00")
    assert _estimated_finish(completed, 60.0) == ""


def test_start_run_background_completes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_module = importlib.import_module("crypto_trendwatching.api.app")
    monkeypatch.setattr(app_module, "build_pipeline", _FakePipeline)

    response = client.post("/runs", json={"zone_id": "infrastructure"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    run_id = body["id"]

    run = client.get(f"/runs/{run_id}").json()
    assert run["status"] == "completed"
