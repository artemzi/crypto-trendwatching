# Архитектура: модули, порты/адаптеры, данные

> **Назначение:** как устроен код и данные. Методику (пороги, правила) см.
> в [methodology.md](./methodology.md); термины — в [glossary.md](./glossary.md).

---

## 1. Общая схема

Гексагональная архитектура: домен и прикладной слой не зависят от внешних сервисов
(HTTP, SQLite, LLM-провайдеры) — они общаются через **порты** (`Protocol`-классы),
реализованные **адаптерами** в `adapters/`.

```
config/          topics.yaml (зоны) · sources.yaml (источники) · onchain.yaml (зона → coins/protocols)
src/crypto_trendwatching/
  domain/        модели (frozen dataclass/pydantic) + порты (Protocols)
  application/   конвейер, фильтр, каталог, верификация, интерпретация, eval, ...
  agent/         agentic loop (инструменты fetch_url/search_web/check_onchain)
  adapters/      RSS, fetch_url, поиск, LLM, on-chain, whale, SQLite, заглушки
  api/           FastAPI + веб-UI + дашборд (M6)
```

Слои зависят только вниз: `api` → `application` → `domain`; `adapters` реализуют
порты `domain`, а `application` их использует через порты (не через конкретные классы).

---

## 2. Доменные модели (`domain/models.py`)

Все модели — `frozen` (pydantic-конфиг или dataclass). Ключевые:

- `Zone`, `Source` — конфиг (pydantic).
- `Signal`, `TrendCandidate`, `ReportedTrend` — сигнал / кандидат / тренд в памяти.
- `EvidenceBinding`, `EvidenceVerdict` — цитата ↔ источник и вердикт проверки.
- `OnChainObservation`, `WhaleTransfer`, `Catalyst`, `TrendVelocity` — обогащение.
- `Interpretation` — блок инвестиционной интерпретации (D-04).
- `ReportRun` — прогон и результат (`report_md`/`report_docx`/`error`).
- `Tool`, `ToolCall`, `AgentTurn` — контракт tool-calling для LLM.

Эмбеддинги — `numpy float16` (`Embedding = npt.NDArray[np.float16]`), в SQLite хранятся
как сырой BLOB (`_embedding_to_blob`/`_blob_to_embedding`).

---

## 3. Порты (`domain/ports.py`)

| Порт | Методы (ключевые) | Адаптер(ы) |
|------|------------------|------------|
| `SourceCollector` | `collect(zone)` | `RssCollector`, `FetchUrlCollector`, `SearchCollector`, `CompositeCollector` |
| `SearchProvider` | `search(query, limit)` | `YandexSearchProvider`, `StubSearch` |
| `Embedder` | `embed(texts)` | `BgeM3Embedder`, `StubEmbedder` |
| `LLMClient` | `complete(...)`, `complete_with_tools(...)` | `OpenAILlmClient` (DeepSeek), `OllamaLlmClient` (ReAct) |
| `OnChainClient` | `tvl`, `volume`, `price`, `change` | `OnChainFacade` (DefiLlama + CoinGecko) |
| `WhaleClient` | `transfers(min_usd, since)` | `WhaleAlertClient`, `StubWhale` |
| `TrendRepository` | сохранение/чтение прогонов, сигналов, кандидатов, evidence, on-chain, whale, catalysts, velocity | `SqliteRepository` |

Подстановка адаптеров — в `application/bootstrap.py`; замена заглушки на реальный
адаптер не трогает ядро (см. `Stub*` в `adapters/stubs.py`).

---

## 4. Прикладной слой (`application/`)

| Модуль | Назначение |
|--------|-----------|
| `pipeline.py` | конвейер 6 фаз; `run()` (sync) и `execute(run_id, zone)` (для фонового запуска) |
| `bootstrap.py` | wiring: сборка адаптеров, каталога, маппинга, порогов |
| `config_loader.py` | `load_zones`/`load_sources`/`load_onchain_mapping` |
| `filter.py` | `normalize_url`, `cosine_similarity`, `filter_by_zone` (дедуп + порог 0.3) |
| `catalog.py` | стабильная нумерация `source_id → N` из `sources.yaml` (D-16) |
| `verify.py` | верификационная цепочка + `VerifyThresholds` |
| `anti_repeat.py` | novelty-gate (косинус 0.85) |
| `interpret.py` | блок интерпретации (D-04) + константа дисклеймера |
| `whale_map.py` | сопоставление whale-трансферов трендам (FR-6) |
| `catalysts.py` | катализатор-календарь (LLM-экстракт + DefiLlama unlocks) |
| `freshness.py` | `trend_velocity` снимки и дельта (FR-11) |
| `eval.py` | золотой сет + precision/recall (D-23, D-24) |
| `retrospective.py` | ретроспективный false-positive (D-26) |
| `circuit_breaker.py` | circuit breaker (fail-open) |
| `render.py` | Markdown-рендерер 8 секций §9 |
| `docx.py` | Markdown → DOCX (`python-docx`) |
| `parsing.py` | безопасный парсинг JSON из ответов LLM |

---

## 5. Agentic loop (`agent/`)

- `tools.py` — `AgentTools`: `fetch_url`, `search_web`, `check_onchain`; возвращают
  текст + структурированные доказательства/on-chain-снимки.
- `loop.py` — `AgentLoop`: до N раундов `complete_with_tools`, исполнение инструментов,
  форсаж финального ответа, дедуп доказательств по URL.

---

## 6. Схема SQLite (`adapters/sqlite_repository.py`)

| Таблица | Что хранит | Примечание |
|---------|-----------|------------|
| `report_runs` | прогоны: статус, `zone_id`, `funnel_json`, `report_md`, `report_docx`, `error` | миграции `zone_id`/`error` |
| `zone_run_results` | чекпоинты фаз прогона по зоне | |
| `trend_items` | сырые сигналы (URL/заголовок/эмбеддинг) | дедуп по URL |
| `trend_candidates` | кандидаты-тренды (`catalog_numbers` как JSON) | |
| `evidence_bindings` | цитата ↔ источник (`candidate_id`) | append-only |
| `evidence_verdicts` | вердикты проверок (`binding_id`/`candidate_id`) | append-only |
| `reported_trends` | память анти-повтора (эмбеддинг) | |
| `onchain_observations` | снимки TVL/объём/цена | `change_7d`/`change_30d` |
| `whale_transfers` | крупные трансферы | append-only |
| `catalysts` | события-катализаторы | |
| `trend_velocity` | freshness-снимки цены/TVL | `UNIQUE(trend_id, metric, subject)` |
| `search_ledger` | журнал поисковых запросов | |

`SqliteRepository` выполняет инкрементальные миграции при старте (`_migrate`).

---

## 7. Поток данных прогона

```
sources.yaml ─▶ RssCollector/FetchUrlCollector ─┐
search (Яндекс) ─▶ SearchCollector ─────────────┼─▶ Signal[]
whale (Whale Alert) ─▶ whale_transfers ─────────┘
   │
   ▼
bge-m3 → embed → filter (дедуп URL + cosine 0.3) → kept signals
   │
   ▼
LLM cluster (чанки по 40) → TrendCandidate[]  (catalog_numbers по каталогу)
   │
   ▼
AgentLoop research → notes + evidence + onchain_observations
   │
   ▼
Verifier (liveness → anti-repeat → relevance → soundness → pump)
   │  ├─ повторы → отклонены (rejected_repeats)
   │  └─ прошли → reported_trends (память) + trend_velocity (freshness)
   ▼
Обогащение: whale-маппинг, интерпретация, катализаторы
   │
   ▼
render (Markdown 8 секций) + docx → report_runs
```

---

## 8. Конфиг (`config/`)

- **`topics.yaml`** — 10 зон (`id`, `name`, `enabled`, `seed_keywords`, профиль).
- **`sources.yaml`** — каталог источников (`id`, `url`, `region`, `method`:
  `rss`/`fetch_url`/`onchain_api`/`whale_api`, `enabled`, `availability_from_rf`).
- **`onchain.yaml`** — зона → `coins` (CoinGecko id) / `protocols` (DefiLlama slug)
  для on-chain-подтверждения (D-18).

Добавление зоны/источника/метрики — правка конфига, не кода (NFR-6); см.
[usage.md](./usage.md).
