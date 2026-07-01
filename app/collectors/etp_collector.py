"""Коллектор коммерческих ЭТП (Сбербанк-АСТ, Росэлторг, Фабрикант,
Портал поставщиков Москвы, Закупки Мособласти и т.д.).

У каждой ЭТП свой способ доступа: у части есть открытый поиск/выгрузка,
у части — только API по договору, часть закрыта капчей/антиботом.
Поэтому это КАРКАС: под каждую площадку по мере получения доступа
реализуйте метод _collect_<площадка>() (через httpx/API или Playwright).

Пока доступов нет — коллектор возвращает пустой список и не роняет сбор.
"""
from __future__ import annotations

import logging

from app.collectors.base import BaseCollector
from app.filters import RawOrder

log = logging.getLogger("collector.etp")


class EtpCollector(BaseCollector):
    type = "etp"

    def collect(self) -> list[RawOrder]:
        log.info(
            "[%s] ЭТП-коллектор — заглушка. Реализуйте доступ (API/парсинг) "
            "после получения доступа к %s.",
            self.source_id,
            self.cfg.get("url", ""),
        )
        return []
