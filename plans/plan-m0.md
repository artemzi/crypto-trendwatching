# Crypto Trendwatching — план реализации M0 (каркас)

> **Статус:** готов к исполнению
> **Дата:** 2026-10-20
> **Связанные документы:** [plan.md](./plan.md), [requirements.md](../docs/requirements.md), [decisions.md](../docs/decisions.md), [AGENT.md](../AGENT.md)

---

## Цель и Definition of Done

Запустить **минимальный сквозной конвейер вхолостую на 1 зоне**: данные пишутся
в SQLite, веб-UI показывает статус. Никакой бизнес-логики качества ещё нет.

**Приёмка (всё должно выполняться БЕЗ API-ключей):**

- `uv sync` ставит зависимости; `pytest` зелёный.
- Команда прогона на зоне `infrastructure`: собрал RSS-элементы → записал в
  `trend_items` (с эмбеддингами-заглушками) → создал строку в `report_runs` со
  статусом `completed`.
- `docker compose up` поднимает веб-UI на `localhost:8080`, видны статусы прогонов.
- Реальный код только там, где не нужны ключи: **RSS, SQLite, FastAPI, загрузка конфига**.

---

## Границы M0 (что реальное, что заглушка)

| Слой | M0 | Почему |
|---|---|---|
| Конфиг (`topics.yaml`, `sources.yaml`) | **реальный** | уже есть, только загрузчик |
| RSS-сбор (`feedparser`) | **реальный** | без ключа |
| SQLite + репозиторий | **реальный** | ядро M0 |
| FastAPI + веб-UI | **реальный** | критерий готовности |
| Эмбеддер | **заглушка** (детерминированный хеш → 1024-dim) | bge-m3 тянет ~2 ГБ модели, подключаем на M1 |
| LLM (DeepSeek/OpenRouter) | **заглушка** | ключа пока нет (F-01) |
| Поиск (Яндекс/Tavily) | **заглушка** | ключа пока нет |
| On-chain / Whale | **заглушка** | нужны на M2/M3 |

Все «заглушки» реализуются за общим портом (Protocol), чтобы на M1/M2 просто
подменить адаптер без правки ядра.

---

## Шаги (по порядку)

1. **Скелет проекта.** `pyproject.toml` (uv, Python 3.11), `.gitignore`, `README.md`,
   пустые пакеты `src/{domain,application,agent,adapters,api}`, `tests/`,
   `docker-compose.yml`. Зависимости: `fastapi`, `uvicorn`, `pydantic`,
   `pydantic-settings`, `numpy`, `openai`, `feedparser`, `httpx`, `pyyaml`;
   dev: `pytest`, `black`, `isort`.

2. **Загрузчик конфига.** Pydantic-модели + читалка `topics.yaml` → `Zone` и
   `sources.yaml` → `Source`. Валидация: обязательные поля; источники с
   `enabled: false` отсеиваются (у Serper/Perplexity уже стоит); у источников с
   `method: rss` обязателен `feed_url`.

3. **Доменные модели** (frozen dataclass): `Zone`, `Source`, `Signal`, `SearchResult`,
   `TrendCandidate`, `ReportedTrend`, `EvidenceBinding`, `WhaleTransfer`, `ReportRun`.

4. **SQLite схема + репозиторий.** DDL ниже; репозиторий с методами save/list
   (эмбеддинг — BLOB float16, туда-обратно через `numpy`).

5. **Порты (Protocols):** `LLMClient`, `Embedder`, `SearchProvider`, `SourceCollector`,
   `OnChainClient`, `WhaleClient`, `TrendRepository`.

6. **Адаптеры.** Реальные: `RssCollector` (feedparser), `SqliteRepository`.
   Заглушки: `StubEmbedder`, `StubLLM`, `StubSearch`, `StubOnChain`, `StubWhale` —
   все за общими портами, логируют вызов. `RssCollector.collect(zone)` собирает
   фиды **всех** включённых (`enabled: true`) источников с `method: rss` (по
   `feed_url`) независимо от категории и помечает каждый сигнал `zone_id` текущего
   прогона; семантическая фильтрация по зоне — на M1 (эмбеддинги). Источники с
   `method: fetch_url`/`search`/`onchain_api`/`whale_api` на M0 не собираются.

7. **Конвейер.** `Pipeline` с фазами `collect → filter → research → synthesize →
   verify → report`. В M0 реальны `collect` + `report` (заглушка отчёта в Markdown),
   остальные — pass-through с логом. Каждая фаза пишет статус в
   `zone_run_results`/`report_runs`.

8. **FastAPI + веб-UI.** Эндпоинты: `POST /runs` (старт, зона из конфига),
   `GET /runs`, `GET /runs/{id}`, `GET /report/{id}`. Минимальная HTML-страница со
   списком прогонов и статусом.

9. **Тесты.** `test_config` (загрузка/валидация), `test_repository` (round-trip сигнала
   с эмбеддингом BLOB), `test_pipeline` (прогон вхолостую на 1 зоне с stub-источником).

10. **Прогон вхолостую.** CLI: `python -m crypto_trendwatching run --zone infrastructure`.
    Проверка Definition of Done.

---

## Схема SQLite (DDL)

```sql
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS trend_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  zone_id TEXT NOT NULL,
  source_id TEXT,
  url TEXT NOT NULL,
  title TEXT,
  summary TEXT,
  published_at TEXT,              -- ISO8601, может быть NULL
  embedding BLOB,                 -- float16, 1024 dims
  extra_json TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_trend_items_zone ON trend_items(zone_id);

CREATE TABLE IF NOT EXISTS reported_trends (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  definition TEXT,
  maturity TEXT,                  -- зарождающийся/растущий/устоявшийся/угасающий
  embedding BLOB,
  first_reported_at TEXT,
  last_reported_at TEXT
);

CREATE TABLE IF NOT EXISTS trend_candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  definition TEXT,
  maturity TEXT,
  catalog_numbers TEXT,           -- JSON-массив номеров источников
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS evidence_bindings (   -- append-only
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  candidate_id INTEGER,
  source_url TEXT NOT NULL,
  quote TEXT,
  catalog_number INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS evidence_verdicts (   -- append-only
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  binding_id INTEGER NOT NULL,
  verdict TEXT NOT NULL,           -- pass/fail
  reason TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS zone_run_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  zone_id TEXT NOT NULL,
  status TEXT NOT NULL,
  checkpoint_json TEXT,
  started_at TEXT,
  finished_at TEXT
);

CREATE TABLE IF NOT EXISTS search_ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  provider TEXT NOT NULL,
  query TEXT NOT NULL,
  results_count INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS report_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  status TEXT NOT NULL,
  funnel_json TEXT,
  report_md TEXT,
  report_docx BLOB,
  started_at TEXT,
  finished_at TEXT
);
```

---

## Порты (набросок)

```python
class LLMClient(Protocol):
    def complete(self, messages: list[dict], *, tools=None, max_tokens=None) -> str: ...


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> "np.ndarray": ...  # (N, 1024) float16


class SearchProvider(Protocol):
    def search(self, query: str, *, limit: int = 10) -> list[SearchResult]: ...


class SourceCollector(Protocol):
    def collect(self, zone: Zone) -> list[Signal]: ...


class OnChainClient(Protocol):
    def tvl(self, protocol: str) -> float: ...
    def volume(self, protocol: str, window: str) -> float: ...


class WhaleClient(Protocol):
    def transfers(self, *, min_usd: float, since) -> list[WhaleTransfer]: ...


class TrendRepository(Protocol):
    def save_signal(self, s: Signal) -> int: ...
    def list_signals(self, zone_id: str) -> list[Signal]: ...
    def save_reported_trend(self, t: ReportedTrend) -> int: ...
    def save_run(self, run: ReportRun) -> int: ...
    def update_run(self, run_id: int, **kwargs) -> None: ...
```

---

## Что остаётся за M0 (переходит в M1+)

- реальный bge-m3 (локальные эмбеддинги),
- эмбеддинг-фильтрация по зоне,
- кластеризация сигналов,
- поисковый веер (Яндекс Search API v2 + Tavily free tier),
- agentic loop (fetch_url / search_web / check_onchain),
- верификационная цепочка с порогами,
- on-chain-подтверждение (DefiLlama/CoinGecko),
- whale-модуль,
- инвестиционная интерпретация + катализатор-календарь,
- `trend_velocity` (freshness-декей, FR-11) — таблица и модель переходят на M3,
- фоновый запуск прогона (POST /runs не блокирует; статус по GET /runs/{id}),
- выровнять версии Python (Dockerfile / .venv / ruff+mypy target на одну, напр. 3.12).
