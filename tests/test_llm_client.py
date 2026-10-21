"""Tests for LLM clients (OpenAI-compatible and native Ollama)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from crypto_trendwatching.adapters.llm import OllamaLlmClient, OpenAILlmClient
from crypto_trendwatching.usage import TokenUsageTracker


def test_openai_client_complete_returns_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = OpenAILlmClient("http://localhost:11434/v1", "qwen3:14b")
    captured: dict[str, Any] = {}

    def fake_create(**kwargs: Any) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="привет"))]
        )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )
    monkeypatch.setattr(client, "_client", fake_client)

    result = client.complete([{"role": "user", "content": "hi"}], max_tokens=100)

    assert result == "привет"
    assert captured["model"] == "qwen3:14b"
    assert captured["max_tokens"] == 100


class OllamaResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {"message": {"content": "привет"}}


class OllamaClient:
    def __init__(self, **kwargs: object) -> None:
        del kwargs

    def __enter__(self) -> OllamaClient:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def post(self, url: str, *, json: dict[str, Any]) -> OllamaResponse:
        del url, json
        return OllamaResponse()


def test_ollama_client_complete_returns_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "Client", OllamaClient)
    client = OllamaLlmClient("http://localhost:11434/v1", "qwen3:14b")
    result = client.complete([{"role": "user", "content": "hi"}])
    assert result == "привет"
    assert client._base_url == "http://localhost:11434"


def test_openai_client_records_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    tracker = TokenUsageTracker()
    client = OpenAILlmClient("http://localhost:11434/v1", "qwen3:14b", usage=tracker)

    def fake_create(**kwargs: Any) -> SimpleNamespace:
        del kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=7),
        )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )
    monkeypatch.setattr(client, "_client", fake_client)

    client.complete([{"role": "user", "content": "hi"}])

    assert tracker.prompt_tokens == 12
    assert tracker.completion_tokens == 7


class _OllamaUsageClient:
    def __init__(self, **kwargs: object) -> None:
        del kwargs

    def __enter__(self) -> _OllamaUsageClient:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def post(self, url: str, *, json: dict[str, Any]) -> SimpleNamespace:
        del url, json
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "message": {"content": "ok"},
                "prompt_eval_count": 30,
                "eval_count": 8,
            },
        )


def test_ollama_client_records_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    tracker = TokenUsageTracker()
    monkeypatch.setattr(httpx, "Client", _OllamaUsageClient)
    client = OllamaLlmClient("http://localhost:11434/v1", "qwen3:14b", usage=tracker)

    client.complete([{"role": "user", "content": "hi"}])

    assert tracker.prompt_tokens == 30
    assert tracker.completion_tokens == 8
