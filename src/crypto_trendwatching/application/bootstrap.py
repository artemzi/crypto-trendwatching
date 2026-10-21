"""Сборка зависимостей конвейера (wiring)."""

from __future__ import annotations

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
from crypto_trendwatching.adapters.stubs import StubSearch, StubWhale
from crypto_trendwatching.adapters.whale import WhaleAlertClient
from crypto_trendwatching.application.catalog import SourceRef, build_catalog
from crypto_trendwatching.application.config_loader import (
    OnChainMapping,
    load_onchain_mapping,
    load_sources,
)
from crypto_trendwatching.application.pipeline import Pipeline
from crypto_trendwatching.application.verify import VerifyThresholds
from crypto_trendwatching.config import settings
from crypto_trendwatching.domain.ports import (
    LLMClient,
    OnChainClient,
    SearchProvider,
    TrendRepository,
    WhaleClient,
)


def build_pipeline(repository: TrendRepository) -> Pipeline:
    """Собрать M3-конвейер: сбор → отбор → кластеризация → агент → верификация → обогащение."""
    sources = load_sources(settings.config_dir / "sources.yaml")
    catalog: dict[str, SourceRef] = build_catalog(sources)
    mapping: dict[str, OnChainMapping] = load_onchain_mapping(
        settings.config_dir / "onchain.yaml"
    )
    llm = build_llm()
    search = build_search_provider()
    onchain = build_onchain()
    whale = build_whale()
    collector = CompositeCollector(
        [
            RssCollector([s for s in sources if s.method == "rss"]),
            FetchUrlCollector([s for s in sources if s.method == "fetch_url"], llm),
            SearchCollector(search),
        ]
    )
    return Pipeline(
        collector=collector,
        repository=repository,
        embedder=BgeM3Embedder(settings.embedder_model),
        llm=llm,
        search=search,
        onchain=onchain,
        whale=whale,
        catalog=catalog,
        onchain_mapping=mapping,
        verify_thresholds=VerifyThresholds(
            anti_repeat_cosine=settings.anti_repeat_threshold,
            pump_price_change_7d=settings.pump_price_change_7d,
            confirmation_change=settings.confirmation_change,
        ),
        research_budget_seconds=settings.research_budget_seconds,
    )


def build_llm() -> LLMClient:
    """Ollama — нативный клиент с think=false; иначе OpenAI-совместимый."""
    if _looks_like_ollama(settings.llm_base_url):
        return OllamaLlmClient(settings.llm_base_url, settings.llm_model)
    return OpenAILlmClient(
        settings.llm_base_url, settings.llm_model, settings.llm_api_key
    )


def build_onchain() -> OnChainClient:
    """DefiLlama (TVL/объёмы) + CoinGecko (цены) — бесплатно, без ключей."""
    return OnChainFacade(
        DefiLlamaClient(), CoinGeckoClient(api_key=settings.coingecko_api_key)
    )


def build_whale() -> WhaleClient:
    """Whale Alert при наличии ключа; иначе заглушка (fail-open, D-20)."""
    if settings.whale_alert_api_key:
        return WhaleAlertClient(settings.whale_alert_api_key)
    return StubWhale()


def _looks_like_ollama(base_url: str) -> bool:
    return any(token in base_url for token in ("11434", "localhost", "127.0.0.1"))


def build_search_provider() -> SearchProvider:
    """Яндекс-поиск, если ключи заданы; иначе заглушка (без запросов)."""
    if settings.yandex_search_api_key and settings.yandex_folder_id:
        return YandexSearchProvider(
            settings.yandex_search_api_key, settings.yandex_folder_id
        )
    return StubSearch()
