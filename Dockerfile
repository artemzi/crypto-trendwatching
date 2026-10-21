# Stage 1: Build dependencies
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
COPY README.md ./
RUN uv sync --frozen --no-dev

# Stage 2: Runtime
FROM python:3.14-slim

RUN groupadd -r crypto && useradd -r -g crypto crypto

COPY --from=builder --chown=crypto:crypto /app/.venv /app/.venv
COPY --chown=crypto:crypto src/ /app/src/
COPY --chown=crypto:crypto config/ /app/config/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

USER crypto
WORKDIR /app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

CMD ["uvicorn", "crypto_trendwatching.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
