# Crypto Trendwatching — план реализации M3 (whale + интерпретация + календарь)

> **Статус:** готов после M2
> **Дата:** 2026-10-21
> **Связанные документы:** [plan.md](./plan.md), [plan-m2.md](./plan-m2.md), [requirements.md](../docs/requirements.md), [decisions.md](../docs/decisions.md), [AGENT.md](../AGENT.md)

---

## Цель и Definition of Done

Превратить отчёт M2 в **полный еженедельный дайджест по структуре §9 требований**:
добавляются whale-модуль (подтверждение/расхождение, не «повторить за китом»),
инвестиционная интерпретация, катализатор-календарь и freshness-декей.

**Приёмка:**

- `uv sync` + `pytest` зелёный.
- Прогон по 10 зонам даёт дайджест со всеми 8 секциями §9: резюме недели, тренды с
  интерпретацией, развитие ранее замеченных (freshness-декей), слабые сигналы,
  whale-активность недели, катализаторы следующей недели, источники, воронка/повторы.
- Whale-маппинг: трансферы ≥ $1M (D-05) сопоставлены трендам как
  подтверждение/расхождение/нейтрально; без «следуй за китом».
- Каждый тренд: блок интерпретации (направление нарратива, горизонт, катализаторы,
  risk-флаги, статус on-chain, дисклеймер — D-04).
- DOCX скачивается кнопкой из веб-UI (`report_docx` заполняется).

---

## Границы M3 (что реальное, что отложено)

| Слой | M3 | Почему |
|---|---|---|
| Whale Alert (free tier) | **реальный** | бесплатный ключ |
| Маппинг whale→тренды (LLM) | **реальный** | FR-6 |
| Интерпретация (LLM) | **реальная** | D-04 |
| Катализатор-календарь | **реальный** (DefiLlama unlocks + LLM-экстракт) | FR-9 |
| Freshness-декей (`trend_velocity`) | **реальный** | FR-11, D-12.4 |
| DOCX-экспорт | **реальный** | D-03 |
| Платные whale/on-chain (Nansen/CryptoQuant/Glassnode/Santiment) | **отложено** | F-02: бесплатные tier |

---

## Шаги (по порядку)

1. [ ] **Whale-порт + адаптер.** Расширить `WhaleClient`: `transfers(min_usd, since) →
   list[WhaleTransfer]` (модель уже есть). `WhaleAlertClient` (ключ
   `WHALE_ALERT_API_KEY`). Fail-open на каждом запросе. Заменить `StubWhale` в
   `bootstrap.py`.

2. [ ] **Хранилище whale.** Таблица `whale_transfers` (append-only) — крупные трансферы
   с amount/asset/адресами/timestamp. Агрегация по окну (неделя) и субъекту.

3. [ ] **Маппинг на тренды.** LLM сопоставляет whale-трансферы (актив/сумма/субъекты)
   с кандидатами-трендами → вердикт «подтверждение/расхождение/нейтрально». Никогда не
   «сигнал повторить сделку» (инвариант).

4. [ ] **Интерпретация (D-04).** LLM генерирует блок на тренд: направление нарратива
   (бычий/нейтральный/медвежий), горизонт (недели/месяцы/кварталы), 3–5 катализаторов с
   датами, 3–5 risk-флагов, статус on-chain-подтверждения (подтверждено/нейтрально/
   расходится), дисклеймер. Вход — evidence M2 + on-chain-метрики + whale-вердикт.

5. [ ] **Катализатор-календарь (FR-9).** Источники: DefiLlama unlocks API (разлоки),
   governance (Snapshot/Tally), LLM-экстракт дат из сигналов (апгрейды, ETF/регуляторы).
   Таблица `catalysts`. Секция отчёта «Катализаторы следующей недели».

6. [ ] **Freshness-декей (FR-11).** Таблица `trend_velocity` (отложена из M0, D-12.4):
   для ранее замеченных трендов — дельта цены/TVL с момента первого сигнала. Секция
   «Развитие ранее замеченных трендов».

7. [ ] **Полный рендерер §9.** Переписать `_report` в `pipeline.py` на все 8 секций,
   включая интерпретацию, whale, календарь, freshness, воронку и отклонённые повторы.

8. [ ] **DOCX-экспорт.** Зависимость `python-docx`. Генерация из Markdown-отчёта →
   `report_runs.report_docx`. Кнопка/эндпоинт скачивания в веб-UI.

9. [ ] **Тесты.** `test_whale` (mock Whale Alert), `test_interpretation` (mock LLM +
    проверка наличия дисклеймера), `test_catalysts`, `test_freshness`, `test_docx`
    (round-trip), `test_pipeline_m3` (сквозной со stub-источниками).

10. [ ] **Веб-UI.** Кнопка скачивания DOCX; показ whale-секции и календаря в отчёте.

---

## Схема данных (новые таблицы)

```sql
CREATE TABLE IF NOT EXISTS whale_transfers (   -- append-only
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  amount_usd REAL NOT NULL,
  asset TEXT,
  from_address TEXT,
  to_address TEXT,
  timestamp TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS catalysts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  candidate_id INTEGER,
  event_date TEXT,
  title TEXT NOT NULL,
  category TEXT,               -- unlock / governance / upgrade / regulatory / macro
  source_url TEXT
);

CREATE TABLE IF NOT EXISTS trend_velocity (   -- freshness-декей (D-12.4)
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  trend_id INTEGER NOT NULL,   -- reported_trends.id
  metric TEXT NOT NULL,        -- price / tvl
  subject TEXT NOT NULL,
  first_value REAL,
  last_value REAL,
  measured_at TEXT NOT NULL
);
```

---

## Что остаётся за M3 (переходит в M4)

- eval-набор и метрики precision/recall,
- ретроспективный false-positive (памп vs тренд через 2–4 недели),
- фоновый запуск `POST /runs` + поллинг статуса,
- мониторинг стоимости/латентности и алерты при отказе провайдеров,
- аудит дисклеймеров во всех каналах выдачи,
- калибровка порогов (анти-повтор, pump-фильтр).

---

## Предусловия

- [ ] `WHALE_ALERT_API_KEY` в `.env` (free tier; проверить лимиты).
- [ ] Зависимость `python-docx` добавлена в `pyproject.toml`.
- [ ] M2 закрыт (evidence + память готовы — вход для интерпретации).

---

## Открытые вопросы (закрыть до/в ходе M3, D-1x)

1. **Whale free tier.** При нехватке лимитов Whale Alert — отложить обогащение до платных
   tier (M4+); Lookonchain (X) исключён D-10.
2. **Катализаторы.** Покрытие DefiLlama unlocks неполное; старт с unlocks + governance,
   расширять LLM-экстрактом.
3. **Freshness.** Каденс снимков (еженедельный) и набор метрик (цена/TVL) — зафиксировать
   в D-записи.
