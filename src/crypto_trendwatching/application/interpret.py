"""Инвестиционная интерпретация тренда (D-04) через LLM."""

from __future__ import annotations

import logging
from typing import Any

from crypto_trendwatching.application.parsing import parse_json_object
from crypto_trendwatching.domain.models import Interpretation, TrendCandidate
from crypto_trendwatching.domain.ports import LLMClient

logger = logging.getLogger(__name__)

DISCLAIMER = "Не является индивидуальной инвестиционной рекомендацией."


def interpret_candidate(
    llm: LLMClient,
    candidate: TrendCandidate,
    onchain_summary: str,
    whale_verdict: str | None,
) -> Interpretation:
    """Сгенерировать блок интерпретации тренда (направление/горизонт/катализаторы/риски)."""
    prompt = (
        "Ты — аналитик крипторынка. Дай инвестиционную интерпретацию тренда. "
        "Верни только JSON-объект: "
        '{"direction": "бычий"|"нейтральный"|"медвежий", '
        '"horizon": "недели"|"месяцы"|"кварталы", '
        '"catalysts": [str, ...3-5], "risk_flags": [str, ...3-5], '
        '"onchain_status": "подтверждено"|"нейтрально"|"расходится"}. '
        "Без пояснений и markdown — только валидный JSON."
    )
    user = (
        f"Тренд: {candidate.name}\n{candidate.definition or ''}\n"
        f"On-chain: {onchain_summary}\n"
        f"Whale-активность: {whale_verdict or 'нет данных'}"
    )
    try:
        raw = llm.complete(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user},
            ],
            max_tokens=800,
        )
        data = parse_json_object(raw)
    except Exception:
        logger.exception("интерпретация не удалась")
        data = {}
    return _to_interpretation(data)


def _to_interpretation(data: dict[str, Any]) -> Interpretation:
    return Interpretation(
        direction=_str_or_none(data.get("direction")),
        horizon=_str_or_none(data.get("horizon")),
        catalysts=_str_list(data.get("catalysts")),
        risk_flags=_str_list(data.get("risk_flags")),
        onchain_status=_str_or_none(data.get("onchain_status")),
        disclaimer=DISCLAIMER,
    )


def _str_or_none(value: Any) -> str | None:
    return str(value) if isinstance(value, str) and value else None


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]
