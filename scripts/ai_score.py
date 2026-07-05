"""Скоринг-проход: берёт неоценённые заказы и записывает ai_rating/ai_reason.

Как использовать:
  * По умолчанию внутри стоит ЭВРИСТИЧЕСКИЙ scorer (без LLM) — чтобы всё работало
    сразу. Claw заменяет функцию score_order() своим вызовом модели (см. CLAW_INTEGRATION.md).
  * Запуск разово:      python -m scripts.ai_score
  * По расписанию:      добавить в cron/таймер рядом со сбором.

Оценивает только записи, где ai_rating IS NULL (новые/непроверенные), чтобы не
жечь токены повторно. Пишет через тот же движок (WAL включён в models.py).
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import Order, SessionLocal, init_db  # noqa: E402

BATCH = 100  # сколько оценивать за один запуск

# --- Эвристический scorer по умолчанию (замените на вызов Claw) ---
_TENDER_SOURCES = {"zakupki_search", "zakupki_mos", "eis"}
_STRONG = ["ищу производств", "пошив", "отшив", "лекал", "футер", "кулирк", "трикотаж"]
_WEAK = ["поставка", "готов", "перепрода", "китай"]
_MOSCOW = ["москва", "московск", "мо ", "подольск", "мытищ"]


def score_order(order: Order):
    """Возвращает (rating:int 0..100, reason:str). ЗАМЕНИТЬ на вызов Claw для точности."""
    text = f"{order.title} {order.description}".lower()
    is_tender = order.source_id in _TENDER_SOURCES
    score = 55 if is_tender else 45
    reasons = []

    for kw in _STRONG:
        if kw in text:
            score += 8
            reasons.append(f"+{kw}")
    for kw in _WEAK:
        if kw in text:
            score -= 12
            reasons.append(f"-{kw}")

    if order.quantity and order.quantity >= 100:
        score += 8
    if is_tender and order.price:
        score += 6
    if order.contact:
        score += 5
    if any(m in (order.region or "").lower() or m in text for m in _MOSCOW):
        score += 8
        reasons.append("+Москва/МО")

    score = max(0, min(100, score))
    reason = ("тендер" if is_tender else "частный") + "; " + (", ".join(reasons[:6]) or "нейтрально")
    return score, reason[:400]


def run(limit: int = BATCH) -> int:
    init_db()
    session = SessionLocal()
    scored = 0
    try:
        rows = (session.query(Order)
                .filter(Order.ai_rating == None)  # noqa: E711
                .order_by(Order.collected_at.desc())
                .limit(limit).all())
        for o in rows:
            rating, reason = score_order(o)
            o.ai_rating = rating
            o.ai_reason = reason
            o.ai_analyzed_at = dt.datetime.utcnow()
            scored += 1
        session.commit()
    finally:
        session.close()
    print(f"Оценено заказов: {scored}")
    return scored


if __name__ == "__main__":
    run()
