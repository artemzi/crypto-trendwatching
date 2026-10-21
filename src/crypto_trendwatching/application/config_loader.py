"""Загрузчик конфига: topics.yaml → Zone, sources.yaml → Source, onchain.yaml → OnChainMapping."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from crypto_trendwatching.domain.models import Source, Zone

_VERSION_KEY = "version"


@dataclass(frozen=True)
class OnChainMapping:
    """Какие монеты/протоколы подтверждают зону on-chain-данными."""

    zone_id: str
    coins: list[str] = field(default_factory=list)
    protocols: list[str] = field(default_factory=list)


def load_zones(path: Path) -> list[Zone]:
    """Загрузить зоны наблюдения из topics.yaml."""
    data = _read_yaml(path)
    return [Zone.model_validate(zone) for zone in data.get("zones", [])]


def load_sources(path: Path) -> list[Source]:
    """Загрузить включённые источники из sources.yaml.

    Источники с ``enabled: false`` отсеиваются (у Serper/Perplexity уже стоит).
    """
    data = _read_yaml(path)
    sources: list[Source] = []
    for category, entries in data.items():
        if category == _VERSION_KEY:
            continue
        if not isinstance(entries, list):
            continue
        for entry in entries:
            source = Source.model_validate({**entry, "category": category})
            if source.enabled:
                sources.append(source)
    return sources


def load_onchain_mapping(path: Path) -> dict[str, OnChainMapping]:
    """Загрузить маппинг зона → монеты/протоколы из onchain.yaml."""
    data = _read_yaml(path)
    result: dict[str, OnChainMapping] = {}
    for entry in data.get("zones", []):
        if not isinstance(entry, dict) or "id" not in entry:
            continue
        result[entry["id"]] = OnChainMapping(
            zone_id=entry["id"],
            coins=list(entry.get("coins", []) or []),
            protocols=list(entry.get("protocols", []) or []),
        )
    return result


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return data if isinstance(data, dict) else {}
