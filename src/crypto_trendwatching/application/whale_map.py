"""Маппинг whale-активности на тренды (FR-6): подтверждение/расхождение/нейтрально."""

from __future__ import annotations

import logging

from crypto_trendwatching.application.parsing import parse_json_object
from crypto_trendwatching.domain.models import TrendCandidate, WhaleTransfer
from crypto_trendwatching.domain.ports import LLMClient

logger = logging.getLogger(__name__)

_VERDICTS = {"подтверждение", "расхождение", "нейтрально"}


def map_whale_verdict(
    llm: LLMClient,
    candidate: TrendCandidate,
    transfers: list[WhaleTransfer],
) -> str | None:
    """Сопоставить whale-трансферы с трендом (никогда не «сигнал повторить сделку»)."""
    if not transfers:
        return None
    transfer_text = "\n".join(
        f"- {t.asset or '?'}: ${t.amount_usd:,.0f} ({t.timestamp or ''})"
        for t in transfers[:20]
    )
    prompt = (
        "Сопоставь whale-активность с трендом. Это подтверждение/расхождение/нейтрально "
        "для тезиса (НЕ сигнал «повторить сделку»). Верни только JSON: "
        '{"verdict": "подтверждение"|"расхождение"|"нейтрально", "reason": "..."}'
    )
    user = f"Тренд: {candidate.name}\n{candidate.definition or ''}\nWhale-трансферы:\n{transfer_text}"
    try:
        raw = llm.complete(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user},
            ],
            max_tokens=256,
        )
        data = parse_json_object(raw)
    except Exception:
        logger.exception("маппинг whale не удался")
        return None
    verdict = data.get("verdict")
    return verdict if isinstance(verdict, str) and verdict in _VERDICTS else None
