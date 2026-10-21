"""Tests for the Whale Alert adapter."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from crypto_trendwatching.adapters.whale import WhaleAlertClient


class _FakeWhaleResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {
            "result": "success",
            "count": 1,
            "transactions": [
                {
                    "symbol": "BTC",
                    "amount_usd": 1_500_000.0,
                    "from": {"address": "0x1", "owner": "exchange"},
                    "to": {"address": "0x2", "owner": None},
                    "timestamp": 1_700_000_000,
                }
            ],
        }


class _FakeClient:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.captured: dict[str, Any] = {}

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def get(self, url: str, *, params: dict[str, Any]) -> _FakeWhaleResponse:
        self.captured = {"url": url, "params": params}
        return _FakeWhaleResponse()


def test_whale_alert_parses_transfer(monkeypatch: pytest.MonkeyPatch) -> None:
    client = WhaleAlertClient("test-key")
    fake = _FakeClient()
    monkeypatch.setattr(httpx, "Client", lambda *_a, **_kw: fake)

    transfers = client.transfers(min_usd=1_000_000, since="2026-10-14T00:00:00+00:00")

    assert len(transfers) == 1
    transfer = transfers[0]
    assert transfer.amount_usd == 1_500_000.0
    assert transfer.asset == "BTC"
    assert transfer.from_address == "0x1"
    assert transfer.to_address == "0x2"
    assert fake.captured["params"]["min_value"] == 1_000_000
    assert "start" in fake.captured["params"]


def test_whale_alert_fail_open(monkeypatch: pytest.MonkeyPatch) -> None:
    client = WhaleAlertClient("test-key")

    class _Failing:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            return None

        def __enter__(self) -> _Failing:
            return self

        def __exit__(self, *_a: Any) -> None:
            return None

        def get(self, _url: str, *, params: dict[str, Any]) -> None:
            del params
            raise RuntimeError("network down")

    monkeypatch.setattr(httpx, "Client", _Failing)
    assert client.transfers(min_usd=1_000_000) == []
