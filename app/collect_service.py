"""Сервис сбора: обход источников -> фильтрация -> дедуп -> сохранение в БД."""
from __future__ import annotations

import logging

from app.config import load_config, settings
from app.collectors.registry import build_collector
from app.filters import FilterEngine
from app.models import Order, SessionLocal, init_db, make_fingerprint

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("collect")


def run_collection() -> dict:
    """Один полный цикл сбора. Возвращает статистику."""
    init_db()
    cfg = load_config()
    fe = FilterEngine(cfg.get("filters", {}))

    stats = {"sources": 0, "raw": 0, "passed": 0, "new": 0, "duplicates": 0, "rejected": 0}
    session = SessionLocal()

    try:
        for src in cfg.get("sources", []):
            if not src.get("enabled"):
                continue
            stats["sources"] += 1

            # проброс кук из .env в конфиг источника
            if src["id"] == "poshivrus" and settings.poshivrus_cookie:
                src["cookie"] = settings.poshivrus_cookie
            if src["id"] == "shveinik" and settings.shveinik_cookie:
                src["cookie"] = settings.shveinik_cookie

            collector = build_collector(src)
            if collector is None:
                log.warning("Неизвестный тип источника: %s", src.get("type"))
                continue

            try:
                raw_orders = collector.collect()
            except Exception as e:  # noqa: BLE001
                log.error("[%s] сбор упал: %s", src["id"], e)
                continue

            for ro in raw_orders:
                stats["raw"] += 1
                ok, reason = fe.matches(ro)
                if not ok:
                    stats["rejected"] += 1
                    continue
                stats["passed"] += 1

                fp = make_fingerprint(ro.source_id, ro.external_key)
                exists = session.query(Order).filter_by(fingerprint=fp).first()
                if exists:
                    stats["duplicates"] += 1
                    continue

                order = Order(
                    fingerprint=fp,
                    source_id=ro.source_id,
                    source_name=ro.source_name,
                    title=ro.title,
                    description=ro.description,
                    quantity=ro.quantity,
                    price=ro.price,
                    region=ro.region,
                    customer=ro.customer,
                    url=ro.url,
                    contact=ro.contact,
                    published_at=ro.published_at,
                    deadline_at=ro.deadline_at,
                    is_new=True,
                )
                session.add(order)
                stats["new"] += 1

        session.commit()
    finally:
        session.close()

    log.info("Итог сбора: %s", stats)
    return stats


if __name__ == "__main__":
    run_collection()
