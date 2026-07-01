"""Базовый класс коллектора."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from app.filters import RawOrder

log = logging.getLogger("collector")


class BaseCollector(ABC):
    """Каждый источник наследует этот класс и реализует collect()."""

    type: str = "base"

    def __init__(self, source_cfg: dict) -> None:
        self.cfg = source_cfg
        self.source_id: str = source_cfg["id"]
        self.source_name: str = source_cfg.get("name", source_cfg["id"])

    @abstractmethod
    def collect(self) -> list[RawOrder]:
        """Возвращает список сырых заказов. Ошибки логируем, не роняем весь сбор."""
        raise NotImplementedError
