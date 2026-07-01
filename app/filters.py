"""Движок фильтрации заказов по параметрам из config.yaml."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RawOrder:
    """Сырой заказ от коллектора — до фильтрации и сохранения."""
    source_id: str
    source_name: str
    external_key: str            # внешний id/url для дедупа
    title: str
    description: str = ""
    quantity: Optional[int] = None
    price: str = ""
    region: str = ""
    customer: str = ""
    url: str = ""
    contact: str = ""
    published_at=None
    deadline_at=None
    extra: dict = field(default_factory=dict)


_QTY_RE = re.compile(r"(\d[\d\s.,]*)\s*(?:шт|штук|ед|единиц|компл|пар)", re.IGNORECASE)


def parse_quantity(text: str) -> Optional[int]:
    """Пытается вытащить количество из текста ('от 500 шт' -> 500)."""
    if not text:
        return None
    m = _QTY_RE.search(text)
    if not m:
        return None
    digits = re.sub(r"[^\d]", "", m.group(1))
    return int(digits) if digits else None


class FilterEngine:
    def __init__(self, filters_cfg: dict) -> None:
        self.min_quantity: int = int(filters_cfg.get("min_quantity", 0))
        self.regions: list[str] = [r.lower() for r in filters_cfg.get("regions", ["*"])]
        self.include = [k.lower() for k in filters_cfg.get("include_keywords", [])]
        self.exclude = [k.lower() for k in filters_cfg.get("exclude_keywords", [])]

    def _text(self, o: RawOrder) -> str:
        return f"{o.title} {o.description} {o.customer}".lower()

    def matches(self, o: RawOrder) -> tuple[bool, str]:
        """Возвращает (прошёл_ли, причина_отказа)."""
        text = self._text(o)

        # 1. Стоп-слова
        for kw in self.exclude:
            if kw in text:
                return False, f"стоп-слово '{kw}'"

        # 2. Тематика (хотя бы одно ключевое слово)
        if self.include and not any(kw in text for kw in self.include):
            return False, "нет тематических ключевых слов"

        # 3. Минимальный объём (если количество распознано)
        qty = o.quantity if o.quantity is not None else parse_quantity(text)
        if qty is not None and qty < self.min_quantity:
            return False, f"объём {qty} < {self.min_quantity}"
        # если qty не распознан — не режем, оставляем менеджеру

        # 4. География
        if "*" not in self.regions and o.region:
            if not any(reg in o.region.lower() for reg in self.regions):
                return False, f"регион '{o.region}' вне списка"

        return True, ""
