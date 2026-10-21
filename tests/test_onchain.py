"""Tests for on-chain adapters (DefiLlama / CoinGecko) with mocked HTTP."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from crypto_trendwatching.adapters.onchain import (
    CoinGeckoClient,
    DefiLlamaClient,
    OnChainFacade,
)

_NOW = 1_700_000_000
_DAY = 86_400


class _FailingClient:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def __enter__(self) -> _FailingClient:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def get(self, _url: str, **_kwargs: Any) -> None:
        raise RuntimeError("network down")


def test_defillama_tvl(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DefiLlamaClient()
    monkeypatch.setattr(client, "_get", lambda _path, **_kw: 123.45)
    assert client.tvl("aave") == 123.45


def test_defillama_volume(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DefiLlamaClient()
    monkeypatch.setattr(client, "_get", lambda _path, **_kw: {"total7d": 500.0})
    assert client.volume("uniswap", "7d") == 500.0


def test_defillama_tvl_change(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DefiLlamaClient()

    def fake_get(path: str, **_kw: Any) -> Any:
        assert path == "/protocol/aave"
        return {
            "tvl": [
                {"date": _NOW - 7 * _DAY, "totalLiquidityUSD": 100.0},
                {"date": _NOW, "totalLiquidityUSD": 120.0},
            ]
        }

    monkeypatch.setattr(client, "_get", fake_get)
    assert client.change("tvl", "aave", 7) == pytest.approx(20.0)


def test_defillama_fail_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "Client", _FailingClient)
    client = DefiLlamaClient()
    assert client.tvl("aave") == 0.0
    assert client.change("tvl", "aave", 7) is None


def test_coingecko_price(monkeypatch: pytest.MonkeyPatch) -> None:
    client = CoinGeckoClient()
    monkeypatch.setattr(
        client, "_get", lambda _path, **_kw: {"bitcoin": {"usd": 80_000.0}}
    )
    assert client.price("bitcoin") == 80_000.0


def test_coingecko_change(monkeypatch: pytest.MonkeyPatch) -> None:
    client = CoinGeckoClient()

    def fake_get(path: str, **_kw: Any) -> Any:
        assert path == "/coins/bitcoin/market_chart"
        return {"prices": [[_NOW - 7 * _DAY, 100.0], [_NOW, 130.0]]}

    monkeypatch.setattr(client, "_get", fake_get)
    assert client.change("price", "bitcoin", 7) == pytest.approx(30.0)


def test_facade_routes_by_metric(monkeypatch: pytest.MonkeyPatch) -> None:
    defillama = DefiLlamaClient()
    coingecko = CoinGeckoClient()
    monkeypatch.setattr(defillama, "_get", lambda _path, **_kw: 10.0)
    monkeypatch.setattr(coingecko, "_get", lambda _path, **_kw: {"x": {"usd": 42.0}})
    facade = OnChainFacade(defillama, coingecko)

    assert facade.tvl("aave") == 10.0
    assert facade.price("x") == 42.0
    assert facade.change("unknown", "x", 7) is None
