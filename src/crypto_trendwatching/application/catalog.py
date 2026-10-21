"""Стабильная нумерация источников: source_id → порядковый номер из sources.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crypto_trendwatching.domain.models import Source


@dataclass(frozen=True)
class SourceRef:
    """Строка каталога: номер, идентификатор, имя и канонический URL источника."""

    number: int
    source_id: str
    name: str
    url: str


def build_catalog(sources: list[Source]) -> dict[str, SourceRef]:
    """Детерминированное отображение source_id → номер по порядку конфига.

    Нумерация строится **один раз на прогон** из порядка ``sources.yaml`` и не зависит
    от порядка появления сигналов (в отличие от старого ``Pipeline._build_catalog``).
    """
    return {
        source.id: SourceRef(
            number=index + 1, source_id=source.id, name=source.name, url=source.url
        )
        for index, source in enumerate(sources)
    }


def catalog_snapshot(catalog: dict[str, SourceRef]) -> list[dict[str, Any]]:
    """Снимок каталога для сохранения в ``funnel_json`` чекпоинта."""
    return [
        {
            "number": ref.number,
            "source_id": ref.source_id,
            "name": ref.name,
            "url": ref.url,
        }
        for ref in sorted(catalog.values(), key=lambda item: item.number)
    ]


def resolve_number(catalog: dict[str, SourceRef], source_id: str | None) -> int | None:
    """Номер источника по его id (None для неизвестных/отсутствующих)."""
    if source_id is None:
        return None
    ref = catalog.get(source_id)
    return ref.number if ref is not None else None
