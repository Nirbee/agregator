"""Миграция существующей БД: добавляет новые колонки, если их нет, и включает WAL.
Безопасно запускать многократно. Данные не теряются.

Запуск:  python -m scripts.migrate
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402
from app.models import engine, init_db  # noqa: E402

# колонка -> SQL-тип для ALTER TABLE
NEW_COLUMNS = {
    "ai_rating": "INTEGER",
    "ai_reason": "TEXT DEFAULT ''",
    "ai_analyzed_at": "DATETIME",
    "published_at": "DATETIME",
    "deadline_at": "DATETIME",
}


def existing_columns(conn):
    rows = conn.execute(text("PRAGMA table_info(orders)")).fetchall()
    return {r[1] for r in rows}


def main():
    init_db()  # создаст таблицу, если БД новая
    with engine.begin() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        have = existing_columns(conn)
        added = []
        for col, coltype in NEW_COLUMNS.items():
            if col not in have:
                conn.execute(text(f"ALTER TABLE orders ADD COLUMN {col} {coltype}"))
                added.append(col)
        # полезные индексы (IF NOT EXISTS — идемпотентно)
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_ai_rating ON orders(ai_rating)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_collected_at ON orders(collected_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_is_archived ON orders(is_archived)"))
    print("Миграция выполнена. Добавлены колонки:", added or "(все уже были)")


if __name__ == "__main__":
    main()
