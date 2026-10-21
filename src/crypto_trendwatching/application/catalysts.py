"""Катализатор-календарь (FR-9): LLM-экстракт дат из сигналов + DefiLlama unlocks."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from crypto_trendwatching.application.parsing import parse_json_list
from crypto_trendwatching.domain.models import Catalyst, Signal, Zone
from crypto_trendwatching.domain.ports import LLMClient

logger = logging.getLogger(__name__)

_CATEGORIES = {"unlock", "governance", "upgrade", "regulatory", "macro"}


def extract_catalysts(
    llm: LLMClient,
    zone: Zone,
    signals: list[Signal],
    run_id: int,
) -> list[Catalyst]:
    """Извлечь предстоящие события (апгрейды/ETF/регуляторы) из сигналов зоны через LLM."""
    if not signals:
        return []
    signal_text = "\n".join(
        f"- {s.title or ''} ({s.published_at or ''})" for s in signals[:60]
    )
    prompt = (
        "Выдели предстоящие события-катализаторы из сигналов. Верни только JSON-массив: "
        '[{"title": str, "event_date": "YYYY-MM-DD"|null, '
        '"category": "unlock"|"governance"|"upgrade"|"regulatory"|"macro"}]. '
        "Только события в будущем (относительно дат сигналов). Без пояснений."
    )
    try:
        raw = llm.complete(
            [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": f"Зона: {zone.name}\nСигналы:\n{signal_text}",
                },
            ],
            max_tokens=1500,
        )
        items = parse_json_list(raw)
    except Exception:
        logger.exception("экстракт катализаторов не удался")
        return []
    result: list[Catalyst] = []
    for item in items:
        catalyst = _to_catalyst(item, run_id)
        if catalyst is not None:
            result.append(catalyst)
    return result


def fetch_unlock_catalysts(run_id: int, *, timeout: float = 20.0) -> list[Catalyst]:
    """Разлоки токенов DefiLlama (fail-open: при недоступности API — пусто)."""
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get("https://api.llama.fi/unlocks")
            response.raise_for_status()
            data = response.json()
    except Exception:
        logger.exception("DefiLlama unlocks недоступны")
        return []
    items = data if isinstance(data, list) else []
    catalysts: list[Catalyst] = []
    for item in items[:20]:
        if not isinstance(item, dict):
            continue
        catalyst = Catalyst(
            run_id=run_id,
            title=str(item.get("name") or item.get("symbol") or "разлок"),
            event_date=_date_or_none(item.get("unlockDate")),
            category="unlock",
        )
        catalysts.append(catalyst)
    return catalysts


def _to_catalyst(item: dict[str, Any], run_id: int) -> Catalyst | None:
    title = item.get("title")
    if not isinstance(title, str) or not title:
        return None
    category = item.get("category")
    return Catalyst(
        run_id=run_id,
        title=title,
        event_date=_date_or_none(item.get("event_date")),
        category=category
        if isinstance(category, str) and category in _CATEGORIES
        else None,
    )


def _date_or_none(value: Any) -> str | None:
    if isinstance(value, (int, float)):
        return str(int(value))
    return str(value) if isinstance(value, str) and value else None
