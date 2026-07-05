"""Веб-портал: карточки заказов, AI-страница и HTTP API для Claw."""
from __future__ import annotations

import secrets
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request, Depends, HTTPException, status, Header, Body
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, headers={"WWW-Authenticate": "Basic"})
    ok_user = secrets.compare_digest(credentials.username, settings.portal_user)
    ok_pass = secrets.compare_digest(credentials.password, settings.portal_password)
    if not (ok_user and ok_pass):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, headers={"WWW-Authenticate": "Basic"})
    return credentials.username


def require_api_key(x_api_key: str = Header(None)):
    """Защита HTTP API по ключу из .env (API_KEY)."""
    if not settings.api_key:
        raise HTTPException(status_code=503, detail="API отключён: задайте API_KEY в .env")
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(status_code=401, detail="Неверный или отсутствующий X-API-Key")
    return True


@app.on_event("startup")
def _startup():
    init_db()


def _sources(cfg):
    return [{"id": s["id"], "name": s.get("name", s["id"]), "enabled": s.get("enabled")}
            for s in cfg.get("sources", [])]


@app.get("/", response_class=HTMLResponse)
def index(request: Request, source: str = "", q: str = "",
          show_archived: int = 0, sort: str = "new", user: str = Depends(auth)):
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
        if sort == "rating":
            query = query.order_by(Order.ai_rating.desc(), Order.collected_at.desc())
        elif sort == "date":
            query = query.order_by(Order.published_at.desc(), Order.collected_at.desc())
        else:
            query = query.order_by(Order.collected_at.desc())
        orders = query.limit(500).all()

        total = session.query(Order).filter(Order.is_archived == False).count()  # noqa: E712
        new_count = session.query(Order).filter(
            Order.is_new == True, Order.is_archived == False).count()  # noqa: E712
        rated_count = session.query(Order).filter(
            Order.ai_rating != None, Order.is_archived == False).count()  # noqa: E711,E712
    finally:
        session.close()

    html = jinja_env.get_template("index.html").render(
        request=request, orders=orders, sources=_sources(cfg),
        cur_source=source, q=q, show_archived=show_archived, sort=sort,
        filters=cfg.get("filters", {}), total=total, new_count=new_count,
        rated_count=rated_count, now=datetime.utcnow(), page="orders")
    return HTMLResponse(html)


@app.get("/ai", response_class=HTMLResponse)
def ai_page(request: Request, source: str = "", min_rating: int = 0, user: str = Depends(auth)):
    cfg = load_config()
    session = SessionLocal()
    try:
        query = session.query(Order).filter(
            Order.is_archived == False, Order.ai_rating != None)  # noqa: E711,E712
        if source:
            query = query.filter(Order.source_id == source)
        if min_rating > 0:
            query = query.filter(Order.ai_rating >= min_rating)
        orders = query.order_by(Order.ai_rating.desc(), Order.collected_at.desc()).limit(500).all()

        rated_count = session.query(Order).filter(
            Order.ai_rating != None, Order.is_archived == False).count()  # noqa: E711,E712
        unscored_count = session.query(Order).filter(
            Order.ai_rating == None, Order.is_archived == False).count()  # noqa: E711,E712
    finally:
        session.close()

    html = jinja_env.get_template("ai.html").render(
        request=request, orders=orders, sources=_sources(cfg),
        cur_source=source, min_rating=min_rating,
        rated_count=rated_count, unscored_count=unscored_count,
        now=datetime.utcnow(), page="ai")
    return HTMLResponse(html)


# ---------------- HTTP API для Claw ----------------

class RateItem(BaseModel):
    id: int
    rating: int
    reason: str = ""


@app.get("/api/orders/unscored")
def api_unscored(limit: int = 100, _: bool = Depends(require_api_key)):
    """Неоценённые карточки (ai_rating IS NULL) для скоринга."""
    session = SessionLocal()
    try:
        rows = (session.query(Order)
                .filter(Order.ai_rating == None, Order.is_archived == False)  # noqa: E711,E712
                .order_by(Order.collected_at.desc()).limit(limit).all())
        return [{"id": o.id, "source_id": o.source_id, "title": o.title,
                 "description": o.description, "quantity": o.quantity, "price": o.price,
                 "region": o.region, "customer": o.customer, "contact": o.contact,
                 "url": o.url} for o in rows]
    finally:
        session.close()


@app.post("/api/orders/rate")
def api_rate(items: list[RateItem] = Body(...), _: bool = Depends(require_api_key)):
    """Записать оценки: тело — список [{id, rating, reason}]."""
    session = SessionLocal()
    updated = 0
    try:
        for it in items:
            o = session.get(Order, it.id)
            if o:
                o.ai_rating = max(0, min(100, int(it.rating)))
                o.ai_reason = (it.reason or "")[:400]
                o.ai_analyzed_at = datetime.utcnow()
                updated += 1
        session.commit()
    finally:
        session.close()
    return {"updated": updated}


# ---------------- Действия портала ----------------

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
    return RedirectResponse(status_code=303, url="/")


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
    return RedirectResponse(status_code=303, url="/")


@app.post("/collect")
def collect_now(user: str = Depends(auth)):
    from app.collect_service import run_collection
    run_collection()
    return RedirectResponse(status_code=303, url="/")


@app.post("/score")
def score_now(user: str = Depends(auth)):
    """Запустить эвристический скоринг неоценённых (заглушка до Claw)."""
    from scripts.ai_score import run
    run()
    return RedirectResponse(status_code=303, url="/ai")
