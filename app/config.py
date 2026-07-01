"""Загрузка настроек из .env и config.yaml."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

CONFIG_PATH = BASE_DIR / "config.yaml"


class Settings:
    """Настройки окружения (из .env)."""

    def __init__(self) -> None:
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/agregator.db")
        self.web_host: str = os.getenv("WEB_HOST", "0.0.0.0")
        self.web_port: int = int(os.getenv("WEB_PORT", "8000"))
        self.portal_user: str = os.getenv("PORTAL_USER", "")
        self.portal_password: str = os.getenv("PORTAL_PASSWORD", "")
        self.collect_interval_minutes: int = int(os.getenv("COLLECT_INTERVAL_MINUTES", "60"))

        # ЕИС
        self.eis_token: str = os.getenv("EIS_TOKEN", "")
        self.eis_org_inn: str = os.getenv("EIS_ORG_INN", "")

        # Telegram
        self.tg_api_id: str = os.getenv("TG_API_ID", "")
        self.tg_api_hash: str = os.getenv("TG_API_HASH", "")
        self.tg_session: str = os.getenv("TG_SESSION", "agregator")
        self.tg_channels: list[str] = [
            c.strip() for c in os.getenv("TG_CHANNELS", "").split(",") if c.strip()
        ]

        # Куки площадок
        self.poshivrus_cookie: str = os.getenv("POSHIVRUS_COOKIE", "")
        self.shveinik_cookie: str = os.getenv("SHVEINIK_COOKIE", "")


def load_config() -> dict[str, Any]:
    """Читает config.yaml (фильтры + источники)."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


settings = Settings()
