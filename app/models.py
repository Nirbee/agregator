"""Модель заказа и подключение к БД."""
from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy import (
    Column, DateTime, Integer, String, Text, Boolean, create_engine, UniqueConstraint, event,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings, BASE_DIR

Base = declarative_base()


class Order(Base):
    """Один заказ/тендер из любого источника."""

    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Уникальный отпечаток для дедупликации (source + внешний id/url/хэш заголовка)
    fingerprint = Column(String(64), unique=True, index=True, nullable=False)

    source_id = Column(String(64), index=True, nullable=False)
    source_name = Column(String(128), nullable=False)

    title = Column(String(512), nullable=False)
    description = Column(Text, default="")
    quantity = Column(Integer, nullable=True)
    price = Column(String(128), default="")
    region = Column(String(256), default="")
    customer = Column(String(512), default="")

    url = Column(String(1024), default="")
    contact = Column(String(512), default="")

    published_at = Column(DateTime, nullable=True)
    deadline_at = Column(DateTime, nullable=True)
    collected_at = Column(DateTime, default=datetime.utcnow, index=True)

    is_new = Column(Boolean, default=True)
    is_archived = Column(Boolean, default=False, index=True)

    # --- Поля AI-оценки (заполняет внешний скоринг, напр. Claw) ---
    ai_rating = Column(Integer, nullable=True, index=True)   # 0..100 или NULL = не оценён
    ai_reason = Column(Text, default="")                     # краткое обоснование
    ai_analyzed_at = Column(DateTime, nullable=True)         # когда оценён

    __table_args__ = (UniqueConstraint("fingerprint", name="uq_fingerprint"),)


def make_fingerprint(source_id: str, external_key: str) -> str:
    raw = f"{source_id}::{external_key}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:64]


# --- инициализация движка ---
_db_url = settings.database_url
if _db_url.startswith("sqlite"):
    (BASE_DIR / "data").mkdir(exist_ok=True)

engine = create_engine(
    _db_url,
    connect_args={"check_same_thread": False} if _db_url.startswith("sqlite") else {},
    future=True,
)


# WAL + таймаут: безопасная одновременная запись приложения и внешнего скоринга (Claw)
if _db_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA busy_timeout=5000;")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(engine)
