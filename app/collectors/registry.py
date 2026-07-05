"""Сопоставление type -> класс коллектора."""
from __future__ import annotations

from app.collectors.base import BaseCollector
from app.collectors.html_collector import HtmlCollector
from app.collectors.eis_collector import EisCollector
from app.collectors.zakupki_search import ZakupkiSearchCollector
from app.collectors.mos_portal import MosPortalCollector
from app.collectors.telegram_collector import TelegramCollector
from app.collectors.etp_collector import EtpCollector

COLLECTOR_TYPES = {
    "html": HtmlCollector,
    "eis_soap": EisCollector,
    "zakupki_search": ZakupkiSearchCollector,
    "mos_portal": MosPortalCollector,
    "telegram": TelegramCollector,
    "etp": EtpCollector,
}


def build_collector(source_cfg):
    ctype = source_cfg.get("type")
    cls = COLLECTOR_TYPES.get(ctype)
    if cls is None:
        return None
    return cls(source_cfg)
