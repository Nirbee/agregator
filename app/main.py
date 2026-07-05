"""Веб-портал: карточки заказов + запуск сбора."""
from __future__ import annotations

import secrets
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import or_

from app.config import settings, load_config
from app.models import Order, SessionLocal, init_db

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="Агрегатор заказов на пошив")
jinja_env = Environment(
    loader=FileSystemLoader(str(BASE_DIR / "templates")),
    autoescape=select_autoescape(["html", "xml"]),
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

security = HTTPBasic(auto_error=False)


def auth(credentials: HTTPBasicCredentials = Depends(security)):
    if not settings.portal_user:
        return "guest"
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            headers={"WWW-Authenticate": "Basic"})
    ok_user = secrets.compare_digest(credentials.username, settings.portal_user)
    ok_pass = secrets.compare_digest(credentials.password, settings.portal_password)
    if not (ok_user and ok_pass):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            headers={"WWW-Authenticate": "Basic"})
    return credentials.username


@app.on_event("startup")
def _startup():
    init_db()


@app.get("/", response_class=HTMLResponse)
def index(request: Request, source: str = "", q: str = "",
          show_archived: int = 0, sort: str = "new", min_rating: int = 0,
          user: str = Depends(auth)):
    cfg = load_config()
    session = SessionLocal()
    try:
        query = session.query(Order)
        if not show_archived:
            query = query.filter(Order.is_archived == False)  # noqa: E712
        if source:
            query = query.filter(Order.source_id == source)
        if q:
            like = f"%{q}%"
            query = query.filter(or_(Order.title.ilike(like), Order.description.ilike(like)))
        if min_rating > 0:
            query = query.filter(Order.ai_rating != None, Order.ai_rating >= min_rating)  # noqa: E711

        if sort == "rating":
            query = query.order_by(Order.ai_rating.desc(), Order.collected_at.desc())
        elif sort == "date":
            query = query.order_by(Order.published_at.desc(), Order.collected_at.desc())
        else:  # "new"
            query = query.order_by(Order.collected_at.desc())

        orders = query.limit(500).all()

        sources = [
            {"id": s["id"], "name": s.get("name", s["id"]), "enabled": s.get("enabled")}
            for s in cfg.get("sources", [])
        ]
        total = session.query(Order).filter(Order.is_archived == False).count()  # noqa: E712
        new_count = session.query(Order).filter(
            Order.is_new == True, Order.is_archived == False  # noqa: E712
        ).count()
        rated_count = session.query(Order).filter(
            Order.ai_rating != None, Order.is_archived == False  # noqa: E711, E712
        ).count()
    finally:
        session.close()

    html = jinja_env.get_template("index.html").render(
        request=request, orders=orders, sources=sources,
        cur_source=source, q=q, show_archived=show_archived,
        sort=sort, min_rating=min_rating,
        filters=cfg.get("filters", {}),
        total=total, new_count=new_count, rated_count=rated_count,
        now=datetime.utcnow(),
    )
    return HTMLResponse(html)


@app.post("/order/{order_id}/archive")
def archive(order_id: int, user: str = Depends(auth)):
    session = SessionLocal()
    try:
        o = session.get(Order, order_id)
        if o:
            o.is_archived = True
            o.is_new = False
            session.commit()
    finally:
        session.close()
    return RedirectResponse("/", status_code=303)


@app.post("/order/{order_id}/seen")
def seen(order_id: int, user: str = Depends(auth)):
    session = SessionLocal()
    try:
        o = session.get(Order, order_id)
        if o:
            o.is_new = False
            session.commit()
    finally:
        session.close()
    return RedirectResponse("/", status_code=303)


@app.post("/collect")
def collect_now(user: str = Depends(auth)):
    """Ручной запуск сбора из портала."""
    from app.collect_service import run_collection
    run_collection()
    return RedirectResponse("/", status_code=303)
