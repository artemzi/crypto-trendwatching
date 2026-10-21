"""Application configuration via pydantic-settings."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_host: str = "127.0.0.1"
    app_port: int = 8080
    log_level: str = "INFO"
    debug: bool = False
    config_dir: Path = Path("config")
    database_path: Path = Path("data/crypto_trends.db")
    embedder_model: str = "BAAI/bge-m3"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen3:14b"
    llm_model_pro: str | None = None
    llm_api_key: str | None = None
    yandex_search_api_key: str | None = None
    yandex_folder_id: str | None = None
    tavily_api_key: str | None = None
    coingecko_api_key: str | None = None
    whale_alert_api_key: str | None = None
    anti_repeat_threshold: float = 0.85
    pump_price_change_7d: float = 30.0
    confirmation_change: float = 10.0


settings = Settings()
