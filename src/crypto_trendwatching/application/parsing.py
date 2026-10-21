"""Разбор JSON из ответов LLM."""

from __future__ import annotations

import json
from typing import Any


def parse_json_list(raw: str) -> list[dict[str, Any]]:
    """Извлечь JSON-массив объектов из ответа LLM (никогда не бросает исключений)."""
    text = raw.strip()
    if text.startswith("```"):
        text = text[text.find("\n") + 1 :] if "\n" in text else text[3:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    data = _loads_or_none(text)
    if data is None:
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end <= start:
            return []
        data = _loads_or_none(text[start : end + 1])
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def parse_json_object(raw: str) -> dict[str, Any]:
    """Извлечь JSON-объект из ответа LLM (никогда не бросает исключений)."""
    text = raw.strip()
    data = _loads_or_none(text)
    if isinstance(data, dict):
        return data
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return {}
    data = _loads_or_none(text[start : end + 1])
    return data if isinstance(data, dict) else {}


def _loads_or_none(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None
