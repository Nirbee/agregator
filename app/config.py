"""Загрузка настроек из .env и config.yaml."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse, unquote

import yaml
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

CONFIG_PATH = BASE_DIR / "config.yaml"


class Settings:
    """Настройки окружения (из .env)."""

    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///./data/agregator.db")
        self.web_host = os.getenv("WEB_HOST", "0.0.0.0")
        self.web_port = int(os.getenv("WEB_PORT", "8000"))
        self.portal_user = os.getenv("PORTAL_USER", "")
        self.portal_password = os.getenv("PORTAL_PASSWORD", "")
        self.collect_interval_minutes = int(os.getenv("COLLECT_INTERVAL_MINUTES", "60"))

        # Ключ для HTTP API (запись оценок от Claw). Пусто = API отключён.
        self.api_key = os.getenv("API_KEY", "").strip()

        # Прокси для доступа к zakupki/ЕИС (http://user:pass@host:port или socks5://...)
        self.proxy_url = os.getenv("PROXY_URL", "").strip()

        # ЕИС
        self.eis_token = os.getenv("EIS_TOKEN", "")
        self.eis_org_inn = os.getenv("EIS_ORG_INN", "")

        # Telegram
        self.tg_api_id = os.getenv("TG_API_ID", "")
        self.tg_api_hash = os.getenv("TG_API_HASH", "")
        self.tg_session = os.getenv("TG_SESSION", "agregator")
        self.tg_channels = [c.strip() for c in os.getenv("TG_CHANNELS", "").split(",") if c.strip()]

        # Куки площадок
        self.poshivrus_cookie = os.getenv("POSHIVRUS_COOKIE", "")
        self.shveinik_cookie = os.getenv("SHVEINIK_COOKIE", "")

    def httpx_proxy(self):
        """Строка прокси для httpx (или None)."""
        return self.proxy_url or None

    def playwright_proxy(self):
        """Словарь прокси для Playwright (или None)."""
        if not self.proxy_url:
            return None
        p = urlparse(self.proxy_url)
        if not p.hostname:
            return None
        server = f"{p.scheme}://{p.hostname}"
        if p.port:
            server += f":{p.port}"
        proxy = {"server": server}
        if p.username:
            proxy["username"] = unquote(p.username)
        if p.password:
            proxy["password"] = unquote(p.password)
        return proxy


def load_config():
    """Читает config.yaml (фильтры + источники)."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


settings = Settings()
