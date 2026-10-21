"""Adapters: collectors, storage, embedder, LLM, search, and M1 stubs."""

from crypto_trendwatching.adapters.collectors import CompositeCollector, SearchCollector
from crypto_trendwatching.adapters.embedder import BgeM3Embedder
from crypto_trendwatching.adapters.fetch_url import FetchUrlCollector
from crypto_trendwatching.adapters.llm import OllamaLlmClient, OpenAILlmClient
from crypto_trendwatching.adapters.onchain import (
    CoinGeckoClient,
    DefiLlamaClient,
    OnChainFacade,
)
from crypto_trendwatching.adapters.rss_collector import RssCollector
from crypto_trendwatching.adapters.search import YandexSearchProvider
from crypto_trendwatching.adapters.sqlite_repository import SqliteRepository
from crypto_trendwatching.adapters.stubs import (
    StubEmbedder,
    StubLLM,
    StubOnChain,
    StubSearch,
    StubWhale,
)

__all__ = [
    "BgeM3Embedder",
    "CoinGeckoClient",
    "CompositeCollector",
    "DefiLlamaClient",
    "FetchUrlCollector",
    "OllamaLlmClient",
    "OnChainFacade",
    "OpenAILlmClient",
    "RssCollector",
    "SearchCollector",
    "SqliteRepository",
    "StubEmbedder",
    "StubLLM",
    "StubOnChain",
    "StubSearch",
    "StubWhale",
    "YandexSearchProvider",
]
