"""Tests for the dashboard data aggregation and JSON endpoints (M6)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from crypto_trendwatching.api.app import create_app
from crypto_trendwatching.application import dashboard as dashboard_lib
from crypto_trendwatching.config import settings
from crypto_trendwatching.domain.models import (
    Catalyst,
    OnChainObservation,
    ReportRun,
    TrendCandidate,
    WhaleTransfer,
)


def test_funnel_stages_ordered() -> None:
    funnel = json.dumps(
        {
            "zone": "defi",
            "phases": {
                "collect": {"signals": 10},
                "filter": {"signals": 8},
                "synthesize": {"candidates": 3},
                "verify": {"passed": 2, "rejected_repeats": 1},
            },
        }
    )
    stages = dashboard_lib.funnel_stages(funnel)
    assert [s["stage"] for s in stages] == ["collect", "filter", "synthesize", "verify"]
    assert stages[0]["count"] == 10
    assert stages[3]["count"] == 2


def test_funnel_stages_empty_or_invalid() -> None:
    assert dashboard_lib.funnel_stages(None) == []
    assert dashboard_lib.funnel_stages("not json") == []


def test_maturity_counts() -> None:
    candidates = [
        TrendCandidate(run_id=1, name="a", maturity="растущий"),
        TrendCandidate(run_id=1, name="b", maturity="растущий"),
        TrendCandidate(run_id=1, name="c"),
    ]
    by_name = {c["name"]: c["count"] for c in dashboard_lib.maturity_counts(candidates)}
    assert by_name["растущий"] == 2
    assert by_name["не указано"] == 1


def test_whale_items_aggregates_by_asset() -> None:
    transfers = [
        WhaleTransfer(amount_usd=100.0, asset="BTC"),
        WhaleTransfer(amount_usd=200.0, asset="BTC"),
        WhaleTransfer(amount_usd=50.0, asset="ETH"),
    ]
    by_asset = {
        i["asset"]: i["amount_usd"] for i in dashboard_lib.whale_items(transfers)
    }
    assert by_asset["BTC"] == 300.0
    assert by_asset["ETH"] == 50.0


def test_figures_are_buildable() -> None:
    stages = [{"stage": "collect", "label": "Сигналы", "count": 10}]
    assert dashboard_lib.funnel_figure(stages) is not None
    assert dashboard_lib.maturity_figure([{"name": "растущий", "count": 1}]) is not None
    assert dashboard_lib.onchain_figure([]) is not None
    assert dashboard_lib.whale_figure([]) is not None
    assert dashboard_lib.catalyst_figure([]) is not None


@pytest.fixture
def client(
    tmp_path: Path, config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setattr(settings, "config_dir", config_dir)
    monkeypatch.setattr(settings, "database_path", tmp_path / "dashboard.db")
    application = create_app()
    with TestClient(application) as test_client:
        yield test_client


def _seed_run(client: TestClient) -> int:
    repository = cast(Any, client.app).state.repository
    run_id: int = repository.save_run(
        ReportRun(
            status="running", zone_id="defi", started_at="2026-10-21T00:00:00+00:00"
        )
    )
    repository.update_run(
        run_id,
        status="completed",
        funnel_json=json.dumps(
            {
                "zone": "defi",
                "phases": {
                    "collect": {"signals": 10},
                    "filter": {"signals": 8},
                    "synthesize": {"candidates": 3},
                    "verify": {"passed": 2, "rejected_repeats": 1},
                },
            }
        ),
    )
    candidate_id = repository.save_trend_candidate(
        TrendCandidate(run_id=run_id, name="Тренд A", maturity="растущий")
    )
    repository.save_onchain_observation(
        OnChainObservation(
            run_id=run_id,
            candidate_id=candidate_id,
            metric="tvl",
            subject="aave",
            value=100.0,
            change_7d=5.0,
            observed_at="2026-10-21T00:00:00+00:00",
        )
    )
    repository.save_whale_transfer(
        run_id, WhaleTransfer(amount_usd=2_000_000.0, asset="ETH")
    )
    repository.save_catalyst(
        Catalyst(
            run_id=run_id, title="Апгрейд", event_date="2026-11-01", category="upgrade"
        )
    )
    return run_id


def test_dashboard_json_endpoints(client: TestClient) -> None:
    run_id = _seed_run(client)

    funnel = client.get(f"/dashboard/{run_id}/funnel").json()
    assert [s["stage"] for s in funnel["funnel"]] == [
        "collect",
        "filter",
        "synthesize",
        "verify",
    ]

    maturity = client.get(f"/dashboard/{run_id}/maturity").json()
    assert maturity["maturity"][0]["name"] == "растущий"

    onchain = client.get(f"/dashboard/{run_id}/onchain").json()
    assert onchain["observations"][0]["subject"] == "aave"

    whale = client.get(f"/dashboard/{run_id}/whale").json()
    assert whale["whale"][0]["asset"] == "ETH"

    catalysts = client.get(f"/dashboard/{run_id}/catalysts").json()
    assert catalysts["catalysts"][0]["title"] == "Апгрейд"


def test_dashboard_page_renders(client: TestClient) -> None:
    run_id = _seed_run(client)
    response = client.get(f"/dashboard/{run_id}")
    assert response.status_code == 200
    assert "Воронка сигналов" in response.text
    assert "plotly.min.js" in response.text


def test_dashboard_missing_run_404(client: TestClient) -> None:
    assert client.get("/dashboard/9999").status_code == 404
    assert client.get("/dashboard/9999/funnel").status_code == 404
