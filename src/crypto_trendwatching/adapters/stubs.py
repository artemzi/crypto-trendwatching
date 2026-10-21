"""Заглушки M0 за общими портами (детерминированный эмбеддер + no-op адаптеры)."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import numpy as np
import numpy.typing as npt

from crypto_trendwatching.domain.models import (
    AgentTurn,
    SearchResult,
    Tool,
    WhaleTransfer,
)
from crypto_trendwatching.domain.ports import Embedding

logger = logging.getLogger(__name__)

_EMBEDDING_DIM = 1024


class StubEmbedder:
    """Детерминированный хеш-эмбеддер → 1024-dim float16 (замена bge-m3 на M0)."""

    def embed(self, texts: list[str]) -> Embedding:
        vectors = np.zeros((len(texts), _EMBEDDING_DIM), dtype=np.float32)
        for index, text in enumerate(texts):
            vectors[index] = _hash_vector(text, _EMBEDDING_DIM)
        return vectors.astype(np.float16)


class StubLLM:
    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: Any = None,
        max_tokens: int | None = None,
    ) -> str:
        logger.info(
            "stub LLM: %d сообщений (tools=%s, max_tokens=%s)",
            len(messages),
            tools is not None,
            max_tokens,
        )
        return ""

    def complete_with_tools(
        self, messages: list[dict[str, Any]], tools: list[Tool]
    ) -> AgentTurn:
        logger.info(
            "stub LLM tools: %d сообщений, %d инструментов", len(messages), len(tools)
        )
        return AgentTurn(content="")


class StubSearch:
    def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        logger.info("stub search: %r (limit=%d)", query, limit)
        return []


class StubOnChain:
    def tvl(self, protocol: str) -> float:
        logger.info("stub on-chain tvl: %s", protocol)
        return 0.0

    def volume(self, protocol: str, window: str) -> float:
        logger.info("stub on-chain volume: %s/%s", protocol, window)
        return 0.0

    def price(self, coin: str) -> float:
        logger.info("stub on-chain price: %s", coin)
        return 0.0

    def change(self, metric: str, subject: str, window_days: int) -> float | None:
        logger.info("stub on-chain change: %s/%s/%d", metric, subject, window_days)
        return None


class StubWhale:
    def transfers(
        self, *, min_usd: float, since: str | None = None
    ) -> list[WhaleTransfer]:
        logger.info("stub whale transfers (min_usd=%s, since=%s)", min_usd, since)
        return []


def _hash_vector(text: str, dim: int) -> npt.NDArray[np.float32]:
    vector = np.zeros(dim, dtype=np.float32)
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    for index in range(dim):
        vector[index] = digest[index % len(digest)] / 127.5 - 1.0
    return vector
