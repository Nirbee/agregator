"""Коллектор Telegram-каналов/ботов (напр. @poshivrus).

Использует Telethon (клиент на базе пользовательского аккаунта).
Требуются TG_API_ID и TG_API_HASH (получить на https://my.telegram.org).
Первый запуск потребует интерактивной авторизации (код из Telegram) —
запустите scripts/tg_login.py один раз, чтобы создать файл сессии.
"""
from __future__ import annotations

import logging

from app.collectors.base import BaseCollector
from app.config import settings
from app.filters import RawOrder, parse_quantity

log = logging.getLogger("collector.telegram")


class TelegramCollector(BaseCollector):
    type = "telegram"

    def collect(self) -> list[RawOrder]:
        if not (settings.tg_api_id and settings.tg_api_hash):
            log.info("[telegram] TG_API_ID/TG_API_HASH не заданы — коллектор пропущен.")
            return []

        try:
            from telethon.sync import TelegramClient
        except ImportError:
            log.warning("[telegram] Telethon не установлен: pip install telethon")
            return []

        channels = settings.tg_channels or []
        results: list[RawOrder] = []

        with TelegramClient(settings.tg_session, int(settings.tg_api_id), settings.tg_api_hash) as client:
            for ch in channels:
                try:
                    for msg in client.iter_messages(ch, limit=50):
                        text = msg.message or ""
                        if not text.strip():
                            continue
                        title = text.strip().split("\n", 1)[0][:200]
                        link = f"https://t.me/{ch.lstrip('@')}/{msg.id}"
                        results.append(
                            RawOrder(
                                source_id=self.source_id,
                                source_name=f"{self.source_name} {ch}",
                                external_key=link,
                                title=title,
                                description=text,
                                quantity=parse_quantity(text),
                                url=link,
                                contact=ch,
                                published_at=msg.date,
                            )
                        )
                except Exception as e:  # noqa: BLE001
                    log.error("[telegram] %s: %s", ch, e)

        log.info("[telegram] собрано сообщений: %d", len(results))
        return results
