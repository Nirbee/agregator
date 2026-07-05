"""Сервис сбора: обход источников -> фильтрация -> дедуп -> сохранение -> авто-архив старых."""
from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import or_

from app.config import load_config, settings
from app.collectors.registry import build_collector
from app.filters import FilterEngine
from app.models import Order, SessionLocal, init_db, make_fingerprint

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("collect")


def cleanup_old(session, cfg) -> int:
    """Архивирует устаревшие карточки: старше max_age_days и/или с прошедшим сроком подачи.
    Возвращает число заархивированных. Данные не удаляются (только is_archived=True)."""
    cc = cfg.get("cleanup", {}) or {}
    max_age_days = int(cc.get("max_age_days", 0) or 0)
    archive_past_deadline = bool(cc.get("archive_past_deadline", False))
    now = dt.datetime.utcnow()

    conds = []
    if max_age_days > 0:
        cutoff = now - dt.timedelta(days=max_age_days)
        # старым считаем по дате публикации, а если её нет — по дате сбора
        conds.append(
            or_(
                Order.published_at < cutoff,
                (Order.published_at == None) & (Order.collected_at < cutoff),  # noqa: E711
            )
        )
    if archive_past_deadline:
        conds.append(Order.deadline_at < now)

    if not conds:
        return 0

    q = session.query(Order).filter(Order.is_archived == False)  # noqa: E712
    q = q.filter(or_(*conds))
    n = 0
    for o in q.all():
        o.is_archived = True
        o.is_new = False
        n += 1
    if n:
        log.info("Авто-архив: убрано устаревших карточек: %d", n)
    return n


def run_collection() -> dict:
    """Один полный цикл сбора. Возвращает статистику."""
    init_db()
    cfg = load_config()
    fe = FilterEngine(cfg.get("filters", {}))

    stats = {"sources": 0, "raw": 0, "passed": 0, "new": 0,
             "duplicates": 0, "rejected": 0, "archived": 0}
    session = SessionLocal()
    seen_fps = set()  # отпечатки, добавленные в этом прогоне (защита от дублей в одном батче)

    try:
        for src in cfg.get("sources", []):
            if not src.get("enabled"):
                continue
            stats["sources"] += 1

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
                if exists or fp in seen_fps:
                    stats["duplicates"] += 1
                    continue
                seen_fps.add(fp)

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

        # авто-архив устаревших
        stats["archived"] = cleanup_old(session, cfg)
        session.commit()
    finally:
        session.close()

    log.info("Итог сбора: %s", stats)
    return stats


if __name__ == "__main__":
    run_collection()
