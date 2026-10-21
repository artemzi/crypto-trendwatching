"""On-chain адаптеры: DefiLlama (TVL/объёмы) и CoinGecko (цены) — бесплатно, без ключей."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_VOLUME_FIELDS = {"24h": "total24h", "7d": "total7d", "30d": "total30d"}
_PAIR_MIN_LENGTH = 2
_MIN_POINTS = 2


def _pct_change(before: float | None, after: float | None) -> float | None:
    """Процентное изменение между двумя величинами (None при делении на ноль)."""
    if before is None or after is None:
        return None
    if before == 0.0:
        return None
    return (after - before) / before * 100.0


class DefiLlamaClient:
    """TVL и DEX-объёмы DefiLlama (без ключа)."""

    def __init__(
        self, base_url: str = "https://api.llama.fi", timeout: float = 20.0
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def tvl(self, protocol: str) -> float:
        data = self._get(f"/tvl/{protocol}")
        if isinstance(data, (int, float)):
            return float(data)
        return 0.0

    def volume(self, protocol: str, window: str) -> float:
        field = _VOLUME_FIELDS.get(window, "total7d")
        data = self._get(
            f"/summary/dexs/{protocol}", params={"dataType": "dailyVolume"}
        )
        if not isinstance(data, dict):
            return 0.0
        value = data.get(field)
        return float(value) if isinstance(value, (int, float)) else 0.0

    def change(self, metric: str, subject: str, window_days: int) -> float | None:
        if metric == "tvl":
            return self._tvl_change(subject, window_days)
        if metric == "volume":
            return self._volume_change(subject, window_days)
        return None

    def _tvl_change(self, protocol: str, window_days: int) -> float | None:
        data = self._get(f"/protocol/{protocol}")
        if not isinstance(data, dict):
            return None
        series = data.get("tvl")
        if not isinstance(series, list):
            return None
        points = [
            (item.get("date"), item.get("totalLiquidityUSD"))
            for item in series
            if isinstance(item, dict)
        ]
        return _change_over_window(points, window_days)

    def _volume_change(self, protocol: str, window_days: int) -> float | None:
        data = self._get(
            f"/summary/dexs/{protocol}", params={"dataType": "dailyVolume"}
        )
        if not isinstance(data, dict):
            return None
        chart = data.get("totalDataChart")
        if not isinstance(chart, list):
            return None
        points = [
            (item.get("date"), item.get("dailyVolume"))
            for item in chart
            if isinstance(item, dict)
        ]
        return _sum_change_over_window(points, window_days)

    def _get(self, path: str, *, params: dict[str, str] | None = None) -> Any:
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(f"{self._base_url}{path}", params=params)
                response.raise_for_status()
                return response.json()
        except Exception:
            logger.exception("DefiLlama запрос не удался: %s", path)
            return None


class CoinGeckoClient:
    """Цены и их изменение через CoinGecko (бесплатный tier, ключ опционален)."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.coingecko.com/api/v3",
        timeout: float = 20.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def price(self, coin: str) -> float:
        data = self._get("/simple/price", params={"ids": coin, "vs_currencies": "usd"})
        if not isinstance(data, dict):
            return 0.0
        entry = data.get(coin)
        value = entry.get("usd") if isinstance(entry, dict) else None
        return float(value) if isinstance(value, (int, float)) else 0.0

    def change(self, metric: str, subject: str, window_days: int) -> float | None:
        del metric
        data = self._get(
            f"/coins/{subject}/market_chart",
            params={"vs_currency": "usd", "days": str(window_days)},
        )
        if not isinstance(data, dict):
            return None
        prices = data.get("prices")
        if not isinstance(prices, list) or not prices:
            return None
        first = _pair_value(prices[0])
        last = _pair_value(prices[-1])
        return _pct_change(first, last)

    def _get(self, path: str, *, params: dict[str, str]) -> Any:
        headers = {"x-cg-demo-api-key": self._api_key} if self._api_key else None
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(
                    f"{self._base_url}{path}", params=params, headers=headers
                )
                response.raise_for_status()
                return response.json()
        except Exception:
            logger.exception("CoinGecko запрос не удался: %s", path)
            return None


class OnChainFacade:
    """Фасад поверх DefiLlama и CoinGecko, реализующий порт ``OnChainClient``."""

    def __init__(self, defillama: DefiLlamaClient, coingecko: CoinGeckoClient) -> None:
        self._defillama = defillama
        self._coingecko = coingecko

    def tvl(self, protocol: str) -> float:
        return self._defillama.tvl(protocol)

    def volume(self, protocol: str, window: str) -> float:
        return self._defillama.volume(protocol, window)

    def price(self, coin: str) -> float:
        return self._coingecko.price(coin)

    def change(self, metric: str, subject: str, window_days: int) -> float | None:
        if metric == "price":
            return self._coingecko.change(metric, subject, window_days)
        if metric in {"tvl", "volume"}:
            return self._defillama.change(metric, subject, window_days)
        return None


def _pair_value(pair: Any) -> float | None:
    """Второй элемент пары [timestamp, value] как float."""
    if isinstance(pair, (list, tuple)) and len(pair) >= _PAIR_MIN_LENGTH:
        value = pair[1]
        return float(value) if isinstance(value, (int, float)) else None
    return None


def _change_over_window(
    points: list[tuple[Any, Any]], window_days: int
) -> float | None:
    """Процентное изменение от точки ``window_days`` назад до последней точки."""
    parsed = [
        (float(ts), float(value))
        for ts, value in points
        if isinstance(ts, (int, float)) and isinstance(value, (int, float))
    ]
    if len(parsed) < _MIN_POINTS:
        return None
    parsed.sort(key=lambda item: item[0])
    latest = parsed[-1][1]
    cutoff = parsed[-1][0] - window_days * 86_400
    past = None
    for ts, value in parsed:
        if ts >= cutoff:
            past = value
            break
    return _pct_change(past, latest)


def _sum_change_over_window(
    points: list[tuple[Any, Any]], window_days: int
) -> float | None:
    """Сравнение суммы значений за последние ``window_days`` и предыдущие."""
    parsed = [
        (float(ts), float(value))
        for ts, value in points
        if isinstance(ts, (int, float)) and isinstance(value, (int, float))
    ]
    if len(parsed) < 2 * window_days:
        return None
    parsed.sort(key=lambda item: item[0])
    now = parsed[-1][0]
    recent = sum(value for ts, value in parsed if ts >= now - window_days * 86_400)
    previous = sum(
        value
        for ts, value in parsed
        if now - 2 * window_days * 86_400 <= ts < now - window_days * 86_400
    )
    return _pct_change(previous, recent)
