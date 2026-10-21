# Crypto Trendwatching — план реализации M2 (исследование + верификация + память)

> **Статус:** готов к исполнению
> **Дата:** 2026-10-21
> **Связанные документы:** [plan.md](./plan.md), [plan-m1.md](./plan-m1.md), [requirements.md](../docs/requirements.md), [decisions.md](../docs/decisions.md), [AGENT.md](../AGENT.md)

---

## Цель и Definition of Done

Перевести конвейер из «черновой дайджест» (M1) в **evidence-first отчёт с проверенными
ссылками и анти-повтором**. Добавляются: agentic loop (исследование), верификационная
цепочка с порогами, on-chain-подтверждение (DefiLlama/CoinGecko), память
(`reported_trends`) и цитирование по номеру каталога `[Ист](N)`.

**Приёмка:**

- `uv sync` + `pytest` зелёный.
- Прогон по **всем 10 зонам**: `collect → filter → cluster → research (agentic loop) →
  verify (цепочка) → report`.
- Каждый тренд-кандидат имеет: проверенные живые ссылки (`evidence_bindings` +
  `evidence_verdicts` с вердиктами), on-chain-снимок (TVL/цена), результат novelty-gate
  против `reported_trends`.
- Отчёт: цитаты по номеру каталога `[Ист](N)`, **номер сохраняется в документе**,
  URL подставляет код (модель не может выдумать ссылку). Повторы не переоткрываются —
  помечаются «ранее замечено».
- В отчёте видны воронка и отклонённые повторы (артефакты §9.8 требований).

---

## Границы M2 (что реальное, что заглушка)

| Слой | M2 | Почему |
|---|---|---|
| On-chain (DefiLlama TVL + CoinGecko цена) | **реальный** | бесплатно, без ключей (D-11) |
| Agentic loop (`fetch_url`/`search_web`/`check_onchain`) | **реальный** | FR-3 |
| Верификационная цепочка | **реальная** | FR-5 |
| Анти-повтор (`reported_trends`) | **реальный** | FR-7, D-11 |
| Pump-фильтр | **реальный** (правило D-08) | D-08 блокирует M2 |
| Whale | **заглушка** | → M3 |
| Инвестиционная интерпретация | **заглушка** | → M3 (D-04) |
| Катализатор-календарь | **заглушка** | → M3 (FR-9) |
| DOCX-экспорт | **заглушка** | → M3 |

Все заглушки остаются за общими портами (`StubWhale` и др.) — подмена на M3 без правки ядра.

---

## Шаги (по порядку)

1. [ ] **Каталог источников (стабильная нумерация).** Детерминированное отображение
   `source_id → N` из `sources.yaml` (порядок конфига), строим **один раз на прогон** и
   кладём в чекпоинт/`funnel_json`. Рендерер подставляет URL по номеру. Это устраняет
   текущий per-run `_build_catalog` в `pipeline.py` (порядокозависимый, меняется между
   зонами/прогонами).

2. [ ] **LLM с tools (исправить замечание M1 №3).** `OpenAILlmClient.complete` сейчас
   не передаёт `tools`. Ввести метод `complete_with_tools(messages, tools) →
   AgentTurn(content, tool_calls)`; для DeepSeek (OpenAI-совместимый) использовать
   нативный function calling. `OllamaLlmClient` — fallback ReAct (JSON-тулзы), т.к.
   нативный tool-calling у Ollama нестабилен.

3. [ ] **On-chain: порт + адаптеры.** Расширить `OnChainClient` (см. «Порты»): добавить
   `price(coin)` и `change(metric, subject, window_days)`. Реализовать
   `DefiLlamaClient` (TVL/объёмы) и `CoinGeckoClient` (цены). Заменить `StubOnChain`
   в `bootstrap.py`. Маппинг «зона → монеты/протоколы» вынести в `config/onchain.yaml`
   (конфиг, а не код — NFR-6).

4. [ ] **Agentic loop (`agent/`).** Инструменты: `fetch_url`, `search_web` (обёртка над
   `SearchProvider`), `check_onchain` (обёртка над `OnChainClient`). Оркестратор: до
   N раундов, бюджет контекста 70% → форсаж финального резюме (plan.md §M2). На вход —
   кандидат + его сигналы; на выход — исследовательские заметки + собранные
   доказательства (URL, цитаты, on-chain-метрики).

5. [ ] **Верификационная цепочка (`application/verify.py`).** Упорядоченные проверки:
   (a) живость URL (httpx HEAD/GET), (b) дедуп (уже есть в `filter.py`), (c) анти-повтор
   (косинус эмбеддинга кандидата против `reported_trends.embedding`, порог 0.85),
   (d) релевантность цитаты (LLM), (e) обоснованность тезиса (LLM), (f) pump-фильтр
   (D-08). Каждая пишет `evidence_bindings` + `evidence_verdicts` (append-only).

6. [ ] **Память (anti-repeat).** Прошедшие проверки кандидаты сохраняются в
   `reported_trends` (name, definition, maturity, embedding, first/last_reported_at).
   Novelty-gate отклоняет кандидатов, косинусно близких к уже зарегистрированным.

7. [ ] **Рендерер отчёта M2.** Evidence-first: тренды с цитатами `[Ист](N)` и
   on-chain-статусом; секции «ранее замечено» (из памяти), «отклонённые повторы»,
   воронка. Замена `_report` в `pipeline.py`.

8. [ ] **Схема данных.** Добавить таблицу `onchain_observations` (см. ниже). Эмбеддинг
   кандидата для anti-repeat считаем на лету из `name + definition` (без новой колонки).

9. [ ] **Тесты.** `test_onchain` (mock ответы DefiLlama/CoinGecko), `test_verify`
   (каждый гейт), `test_anti_repeat` (порог косинуса), `test_catalog` (стабильность
   нумерации), `test_agent_loop` (mock tools), `test_pipeline_m2` (stub-источник +
   mock-LLM сквозной прогон).

10. [ ] **Веб-UI.** Показ evidence/вердиктов кандидата (`GET /runs/{id}/candidates`
    расширить полем evidence).

---

## Схема данных (новые таблицы)

```sql
CREATE TABLE IF NOT EXISTS onchain_observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  candidate_id INTEGER,
  metric TEXT NOT NULL,        -- tvl / volume / price
  subject TEXT NOT NULL,       -- protocol id / coin id (из config/onchain.yaml)
  value REAL,
  change_7d REAL,
  change_30d REAL,
  observed_at TEXT NOT NULL
);
```

`evidence_bindings` / `evidence_verdicts` / `reported_trends` уже существуют — M2 наполняет
их данными (реализует запись, которой в M1 не было).

---

## Порты (набросок изменений)

```python
class OnChainClient(Protocol):
    def tvl(self, protocol: str) -> float: ...
    def volume(self, protocol: str, window: str) -> float: ...
    def price(self, coin: str) -> float: ...
    def change(self, metric: str, subject: str, window_days: int) -> float | None: ...


class LLMClient(Protocol):
    def complete(self, messages, *, tools=None, max_tokens=None) -> str: ...
    def complete_with_tools(self, messages, tools) -> AgentTurn: ...
```

---

## Что остаётся за M2 (переходит в M3)

- whale-модуль (Whale Alert, маппинг на тренды),
- инвестиционная интерпретация (D-04),
- катализатор-календарь (FR-9),
- freshness-декей / `trend_velocity` (FR-11, отложено D-12.4),
- DOCX-экспорт (D-03),
- полный дайджест по §9 (все 8 секций).

---

## Предусловия

- [ ] On-chain: DefiLlama/CoinGecko — без ключей; `config/onchain.yaml` создан.
- [ ] Прод-LLM: DeepSeek с поддержкой function calling (проверить на одном прогоне).
- [ ] Решения по открытым вопросам ниже зафиксировать в `decisions.md` (D-16+).

---

## Открытые вопросы (закрыть до/в ходе M2, D-16+)

1. **Нумерация каталога.** Предлагается порядок конфига (стабильный); номер — снимок на
   прогон, хранится в `funnel_json`, старые отчёты не ломаются.
2. **Порог анти-повтора.** Косинус 0.85 как старт; калибровать на eval в M4.
3. **Маппинг on-chain.** `config/onchain.yaml` (зона → coins/protocols) против
   расширения `topics.yaml`. Предлагается отдельный файл.
4. **Tool-calling.** Нативный function calling DeepSeek против ReAct-JSON. Рекомендация:
   нативный, fallback ReAct.
