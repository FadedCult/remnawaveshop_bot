from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "RemnaShop"
    environment: str = "dev"
    base_url: str = "http://localhost:8080"
    timezone: str = "Europe/Moscow"

    database_url: str = "sqlite+aiosqlite:///./data/remnashop.db"

    bot_token: str = ""
    bot_admin_ids: list[int] = Field(default_factory=list)
    support_username: str = "support"

    admin_username: str = "admin"
    admin_password: str = "change-me"
    admin_password_hash: str | None = None
    session_secret: str = "change-me"

    web_host: str = "0.0.0.0"
    web_port: int = 8080
    web_domain: str = "localhost"

    remnawave_base_url: str = "https://remnawave.example.com/api/v1"
    remnawave_api_key: str = ""
    remnawave_timeout: int = 20
    remnawave_users_path: str = "/users"
    remnawave_subscriptions_path: str = "/subscriptions"
    remnawave_servers_path: str = "/servers"
    remnawave_nodes_path: str = "/nodes"
    remnawave_stats_path: str = "/stats"

    payment_provider: str = "none"
    payment_api_key: str | None = None
    payment_webhook_secret: str | None = None

    backup_dir: str = "./backups"

    @field_validator("bot_admin_ids", mode="before")
    @classmethod
    def parse_bot_admin_ids(cls, value: Any) -> list[int]:
        if value is None:
            return []
        if isinstance(value, (int, float)):
            return [int(value)]
        if isinstance(value, list):
            return [int(v) for v in value]
        if isinstance(value, (tuple, set)):
            return [int(v) for v in value]
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return []
            if cleaned.startswith("["):
                try:
                    parsed = json.loads(cleaned)
                    if isinstance(parsed, list):
                        return [int(v) for v in parsed]
                except json.JSONDecodeError:
                    pass
            raw = [part.strip() for part in cleaned.split(",") if part.strip()]
            return [int(v) for v in raw]
        raise ValueError("BOT_ADMIN_IDS must be a comma-separated list of integers")

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"prod", "production"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
