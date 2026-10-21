# Руководство пользователя

> Как запустить систему, читать дайджест и расширять конфиг (зоны/источники/метрики).

---

## 1. Установка и запуск

Требования: Python 3.11+, [uv](https://docs.astral.sh/uv/).

```bash
uv sync                                   # зависимости
cp .env.example .env                      # заполнить ключи (LLM, Яндекс-поиск, опц. whale)
```

Запуск конвейера (CLI, синхронно):

```bash
uv run crypto-trendwatching run --zone infrastructure   # одна зона
uv run crypto-trendwatching run --all                   # все 10 зон
uv run crypto-trendwatching eval                        # precision/recall по золотому сету
uv run crypto-trendwatching retro                       # ретроспектива pump-флагов
```

Веб-UI (FastAPI) на `http://localhost:8080`:

```bash
uv run crypto-trendwatching serve
# или
docker compose up
```

В веб-UI: кнопки запуска по зонам (с подтверждением), фильтр по статусу (по умолчанию
«Завершённые»), просмотр отчёта (`Отчёт`), скачивание DOCX, удаление прогона.
`POST /runs` выполняется в фоне и возвращает `run_id` сразу (D-25); статус — по
`GET /runs/{id}`.

Проверки:

```bash
make check                                 # lint + тесты + security
uv run pytest                              # тесты + coverage
```

---

## 2. Чтение дайджеста

Отчёт состоит из 8 секций (§9 требований):

1. **Резюме недели** — ключевые сдвиги по зоне.
2. **Тренды** — каждый тренд с зрелостью, определением, цитатами по каталогу
   `[Ист](N)`, on-chain-статусом, whale-вердиктом и блоком интерпретации
   (направление/горизонт/катализаторы/риски/дисклеймер).
3. **Развитие ранее замеченных** — дельта цены/TVL с первого сигнала (freshness).
4. **Слабые сигналы** — сигналы, не вошедшие в кластеры.
5. **Whale-активность недели** — крупные трансферы (≥ $1M).
6. **Катализаторы следующей недели** — события с датами (unlock/upgrade/regulatory/…).
7. **Источники** — каталог `N. имя — URL` (на `[Ист](N)` ссылаются цитаты).
8. **Отклонённые повторы + воронка** — что отсеялось и счётчики фаз.

Формат дат в UI: `Д/М/Г Ч:М:С` (локальный часовой пояс). Дисклеймер «не является
индивидуальной инвестиционной рекомендацией» — в отчёте, веб-UI и DOCX.

---

## 3. Добавить зону

`config/topics.yaml` — добавить запись в `zones`:

```yaml
zones:
  - id: nft
    name: NFT и гейминг
    enabled: true
    seed_keywords: [nft, gaming, marketplace, royalties]
```

И (для on-chain-подтверждения) `config/onchain.yaml`:

```yaml
zones:
  - id: nft
    coins: [immutable-x, the-sandbox]
    protocols: []
```

Кода править не нужно (NFR-6).

---

## 4. Добавить источник

`config/sources.yaml` — добавить в нужную категорию:

```yaml
news:
  - id: example
    name: Example News
    url: https://example.com/
    region: EN
    method: rss            # rss | fetch_url | onchain_api | whale_api
    enabled: true
    availability_from_rf: "да"
```

- `method: rss` — потребует `feed_url`.
- `method: fetch_url` — страница парсится LLM.
- `enabled: false` — источник исключается из прогона.

Нумерация каталога `[Ист](N)` строится из порядка этого файла (D-16).

---

## 5. Добавить on-chain-метрику

`config/onchain.yaml`: укажи `coins` (id CoinGecko) и/или `protocols` (slug DefiLlama)
для зоны. Агент в фазе research получит подсказку и сможет вызвать `check_onchain`
(tvl/volume/price). Пороги on-chain-подтверждения — `.env` (`CONFIRMATION_CHANGE` и др.,
D-27).

---

## 6. Настройка порогов

Через `.env` (без правки кода, D-27):

```bash
ANTI_REPEAT_THRESHOLD=0.85     # анти-повтор (косинус)
PUMP_PRICE_CHANGE_7D=30.0      # pump-фильтр: рост цены за 7д, %
CONFIRMATION_CHANGE=10.0       # on-chain-подтверждение: рост TVL/объёмов, %
```

---

## 7. Оценка качества

- `eval` — precision/recall выхода конвейера против `data/eval/golden.yaml`
  (3 приоритетные зоны D-09).
- `retro` — проверка pump-флагов: цена вернулась → «памп», закрепилась → «тренд»
  (D-26).
