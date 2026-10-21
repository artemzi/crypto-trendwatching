"""LLM-клиенты: OpenAI-совместимый (DeepSeek) и нативный Ollama (ReAct-фолбэк)."""

from __future__ import annotations

import json
import logging
from typing import Any, cast

import httpx
from openai import OpenAI

from crypto_trendwatching.domain.models import AgentTurn, Tool, ToolCall

logger = logging.getLogger(__name__)


def _tools_to_openai(tools: list[Tool]) -> list[dict[str, Any]]:
    """Конвертация описаний инструментов в формат OpenAI function calling."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in tools
    ]


def _tool_calls_from_openai(message: Any) -> list[ToolCall]:
    """Разбор tool_calls ответа OpenAI-совместимого API."""
    calls: list[ToolCall] = []
    for call in message.tool_calls or []:
        arguments = _loads_or_default(call.function.arguments)
        calls.append(
            ToolCall(id=call.id or "", name=call.function.name, arguments=arguments)
        )
    return calls


def _loads_or_default(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


class OpenAILlmClient:
    """Тонкий клиент поверх OpenAI-совместимого API (DeepSeek и др.)."""

    def __init__(self, base_url: str, model: str, api_key: str | None = None) -> None:
        self._client = OpenAI(base_url=base_url, api_key=api_key or "not-needed")
        self._model = model

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Any = None,
        max_tokens: int | None = None,
    ) -> str:
        logger.info(
            "LLM complete: model=%s, messages=%d, tools=%s",
            self._model,
            len(messages),
            tools is not None,
        )
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": cast(Any, messages),
            "max_tokens": max_tokens,
        }
        if tools is not None:
            kwargs["tools"] = tools
        response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    def complete_with_tools(
        self, messages: list[dict[str, Any]], tools: list[Tool]
    ) -> AgentTurn:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=cast(Any, messages),
            tools=cast(Any, _tools_to_openai(tools)),
        )
        message = response.choices[0].message
        return AgentTurn(
            content=message.content or "",
            tool_calls=_tool_calls_from_openai(message),
        )


class OllamaLlmClient:
    """Нативный клиент Ollama (`/api/chat`); tool-calling — ReAct-JSON."""

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        think: bool = False,
        timeout: float = 600.0,
    ) -> None:
        root = base_url.rstrip("/")
        if root.endswith("/v1"):
            root = root[: -len("/v1")]
        self._base_url = root
        self._model = model
        self._think = think
        self._timeout = timeout

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Any = None,
        max_tokens: int | None = None,
    ) -> str:
        del tools
        logger.info(
            "Ollama complete: model=%s, messages=%d, think=%s",
            self._model,
            len(messages),
            self._think,
        )
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "think": self._think,
        }
        if max_tokens is not None:
            payload["options"] = {"num_predict": max_tokens}
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(f"{self._base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        return _extract_content(data)

    def complete_with_tools(
        self, messages: list[dict[str, Any]], tools: list[Tool]
    ) -> AgentTurn:
        react_messages = _react_messages(messages, tools)
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": react_messages,
                    "stream": False,
                    "think": self._think,
                },
            )
            response.raise_for_status()
            data = response.json()
        return _parse_react(_extract_content(data))


def _extract_content(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    message = data.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return content if isinstance(content, str) else ""


def _react_instruction(tools: list[Tool]) -> str:
    definitions = json.dumps(
        [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in tools
        ],
        ensure_ascii=False,
    )
    return (
        "Ты — исследовательский агент. Ты можешь вызывать инструменты. "
        "Отвечай СТРОГО одним JSON-объектом (без markdown):\n"
        "- если нужен инструмент: "
        '{"tool_calls": [{"name": "<имя>", "arguments": {}}]}\n'
        '- если ответ готов: {"final": "<текст>"}\n'
        f"Доступные инструменты: {definitions}"
    )


def _react_messages(
    messages: list[dict[str, Any]], tools: list[Tool]
) -> list[dict[str, Any]]:
    system_text = next(
        (
            message["content"]
            for message in messages
            if message.get("role") == "system" and message.get("content")
        ),
        "",
    )
    combined = f"{system_text}\n\n{_react_instruction(tools)}".strip()
    result: list[dict[str, Any]] = [{"role": "system", "content": combined}]
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if role == "system":
            continue
        if role == "tool":
            result.append(
                {"role": "user", "content": f"Результат инструмента: {content or ''}"}
            )
            continue
        if role == "assistant":
            tool_calls = message.get("tool_calls")
            text = content or ""
            if tool_calls:
                text = _format_tool_calls(tool_calls)
            result.append({"role": "assistant", "content": text})
            continue
        result.append({"role": "user", "content": content or ""})
    return result


def _format_tool_calls(tool_calls: list[dict[str, Any]]) -> str:
    rendered = []
    for call in tool_calls:
        function = call.get("function", {}) if isinstance(call, dict) else {}
        name = function.get("name") if isinstance(function, dict) else None
        arguments = function.get("arguments") if isinstance(function, dict) else "{}"
        rendered.append(
            f'{{"tool_calls": [{{"name": "{name}", "arguments": {arguments}}}]}}'
        )
    return "\n".join(rendered)


def _parse_react(content: str) -> AgentTurn:
    text = content.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end < start:
        return AgentTurn(content=text)
    data = _loads_or_default(text[start : end + 1])
    if "tool_calls" in data:
        calls = []
        for index, call in enumerate(data.get("tool_calls", [])):
            if not isinstance(call, dict):
                continue
            arguments = call.get("arguments")
            calls.append(
                ToolCall(
                    id=f"call_{index}",
                    name=str(call.get("name", "")),
                    arguments=arguments if isinstance(arguments, dict) else {},
                )
            )
        return AgentTurn(tool_calls=calls)
    if "final" in data:
        return AgentTurn(content=str(data["final"]))
    return AgentTurn(content=text)
