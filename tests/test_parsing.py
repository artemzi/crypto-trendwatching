"""Tests for LLM JSON parsing."""

from crypto_trendwatching.application.parsing import parse_json_list


def test_parses_plain_json_list() -> None:
    raw = '[{"name": "A"}, {"name": "B"}]'
    assert parse_json_list(raw) == [{"name": "A"}, {"name": "B"}]


def test_parses_code_fenced_json() -> None:
    raw = '```json\n[{"name": "A"}]\n```'
    assert parse_json_list(raw) == [{"name": "A"}]


def test_parses_json_wrapped_in_prose() -> None:
    raw = 'Вот результат:\n[{"name": "A"}]\nНадеюсь, помог.'
    assert parse_json_list(raw) == [{"name": "A"}]


def test_returns_empty_on_garbage() -> None:
    assert parse_json_list("no json here") == []
