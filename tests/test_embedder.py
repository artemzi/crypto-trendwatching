"""Tests for the bge-m3 embedder."""

import numpy as np
import numpy.typing as npt

from crypto_trendwatching.adapters.embedder import BgeM3Embedder


class FakeModel:
    def encode(self, texts: list[str], **kwargs: object) -> npt.NDArray[np.float32]:
        del kwargs
        return np.zeros((len(texts), 1024), dtype=np.float32)


def test_embed_shapes_and_dtype() -> None:
    embedder = BgeM3Embedder("fake-model")
    embedder._model = FakeModel()
    result = embedder.embed(["first", "second", "third"])
    assert result.shape == (3, 1024)
    assert result.dtype == np.float16


def test_embed_empty_returns_empty() -> None:
    embedder = BgeM3Embedder("fake-model")
    result = embedder.embed([])
    assert result.shape == (0, 1024)
    assert result.dtype == np.float16
