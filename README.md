# Crypto Trendwatching

Персональный исследовательский дайджест по крипторынку: evidence-first, анти-повтор
с памятью, on-chain-подтверждение, whale-активность, инвестиционная интерпретация,
катализатор-календарь и DOCX-экспорт.

> **Статус: M0–M6 завершены.** Полный конвейер на 10 зонах + верификация ссылок +
> анти-повтор + интерпретация + whale + календарь + eval/метрики + фоновый запуск +
> интерактивный дашборд (Plotly). Документация — в [docs/](docs/).

## Требования

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

## Установка

```bash
uv sync
cp .env.example .env   # заполнить LLM_API_KEY, YANDEX_SEARCH_* и (опц.) WHALE_ALERT_API_KEY
```

## Запуск

Прогон конвейера по одной зоне или по всем 10:

```bash
uv run crypto-trendwatching run --zone infrastructure
uv run crypto-trendwatching run --all
```

Веб-UI (FastAPI) на `http://localhost:8080` — запуск по зонам, просмотр отчёта,
скачивание DOCX, удаление прогона, фильтр по статусу:

```bash
uv run crypto-trendwatching serve
# или через docker compose
docker compose up
```

Оценка качества и ретроспектива:

```bash
uv run crypto-trendwatching eval     # precision/recall по data/eval/golden.yaml
uv run crypto-trendwatching retro    # проверка pump-флагов (памп vs тренд)
```

## Тесты и проверки

```bash
uv run pytest          # тесты + coverage
uv run ruff check .    # линтер
uv run ruff format .   # форматтер
uv run mypy .          # типы
make check             # lint + тесты + security
```

## Структура

```
config/                # topics.yaml (зоны), sources.yaml (источники), onchain.yaml (зона → coins/protocols)
data/eval/             # золотой сет для метрик качества
src/crypto_trendwatching/
  domain/              # модели + порты (Protocols)
  application/         # конвейер, верификация, интерпретация, eval, ...
  agent/               # agentic loop (fetch_url / search_web / check_onchain)
  adapters/            # RSS, fetch_url, поиск, LLM, on-chain, whale, SQLite, заглушки
  api/                 # FastAPI + веб-UI
tests/
```

## Документация

Полная документация — в папке [docs/](docs/):

- [docs/methodology.md](docs/methodology.md) — методика: фазы, верификация, пороги.
- [docs/architecture.md](docs/architecture.md) — модули, порты/адаптеры, схема данных.
- [docs/usage.md](docs/usage.md) — как запускать, читать дайджест, расширять конфиг.
- [docs/glossary.md](docs/glossary.md) — глоссарий терминов.
- [docs/requirements.md](docs/requirements.md) — требования (скоуп, FR/NFR, формат отчёта §9).
- [docs/decisions.md](docs/decisions.md) — журнал решений (D-xx/F-xx).
- [docs/checklist.md](docs/checklist.md) — текущее состояние и гейты фаз.
- [AGENT.md](AGENT.md) — как работать с проектом.

## Статус фаз

- **M0** — конвейер на 1 зоне, данные в SQLite, веб-UI. ✅
- **M1** — сбор → отбор → кластеризация → дайджест по 10 зонам. ✅
- **M2** — верификация ссылок + анти-повтор с памятью. ✅
- **M3** — полный дайджест §9: интерпретация + whale + календарь + DOCX. ✅
- **M4** — eval/метрики + фоновый запуск + мониторинг + дисклеймеры. ✅
- **M5** — документация методики и архитектуры. ✅
- **M6** — интерактивный веб-дашборд (Plotly). ✅
