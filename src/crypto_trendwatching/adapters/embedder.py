"""Реальный эмбеддер bge-m3 (локальный, кросс-язычный RU↔EN)."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from crypto_trendwatching.domain.ports import Embedding

logger = logging.getLogger(__name__)

_EMBEDDING_DIM = 1024


class BgeM3Embedder:
    """bge-m3 через sentence-transformers; модель грузится лениво при первом embed."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model: Any = None

    def embed(self, texts: list[str]) -> Embedding:
        if not texts:
            return np.zeros((0, _EMBEDDING_DIM), dtype=np.float16)
        model = self._load()
        vectors = model.encode(texts, normalize_embeddings=True)
        return np.asarray(vectors, dtype=np.float16)

    def _load(self) -> Any:
        if self._model is None:
            logger.info("загрузка модели эмбеддингов %s", self._model_name)
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415 — ленивая загрузка torch

            self._model = SentenceTransformer(self._model_name)
        return self._model
