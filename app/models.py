"""Модель заказа и подключение к БД."""
from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy import (
    Column, DateTime, Integer, String, Text, Boolean, create_engine, UniqueConstraint,
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

    source_id = Column(String(64), index=True, nullable=False)   # poshivrus, eis, ...
    source_name = Column(String(128), nullable=False)            # человекочитаемое

    title = Column(String(512), nullable=False)
    description = Column(Text, default="")
    quantity = Column(Integer, nullable=True)                    # шт, если распознано
    price = Column(String(128), default="")                     # НМЦК/бюджет, как текст
    region = Column(String(256), default="")
    customer = Column(String(512), default="")                  # заказчик

    url = Column(String(1024), default="")                     # ссылка на заказ
    contact = Column(String(512), default="")                  # телефон/email/@ник

    published_at = Column(DateTime, nullable=True)              # дата публикации заказа
    deadline_at = Column(DateTime, nullable=True)              # срок подачи
    collected_at = Column(DateTime, default=datetime.utcnow)

    is_new = Column(Boolean, default=True)                     # для подсветки в портале
    is_archived = Column(Boolean, default=False)

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
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(engine)
