"""Коллектор «Портал поставщиков Москвы» (zakupki.mos.ru) — котировочные сессии.

ВНИМАНИЕ: включать после проверки на сервере (домен доступен из РФ, возможно
через прокси). Селекторы карточек заданы предположительно — сверьте реальную
вёрстку в DevTools и поправьте в config.yaml (секция selectors у источника).

Логика идентична zakupki: перебор поисковых запросов -> карточки -> RawOrder.
Проксирование — через PROXY_URL (settings), как и у остальных.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

from app.collectors.base import BaseCollector
from app.config import settings
from app.filters import RawOrder, parse_quantity

log = logging.getLogger("collector.mos")

BASE = "https://zakupki.mos.ru/auction/search"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

DEFAULT_SELECTORS = {
    "card": ".card, .search-results__item, [data-test='auction-card']",
    "title": ".card__title, .auction-card__name, h3",
    "price": ".card__price, .auction-card__price",
    "link": "a@href",
}
_NUM_RE = re.compile(r"(\d{6,})")


def _txt(node, sel):
    el = node.select_one(sel)
    return el.get_text(" ", strip=True) if el else ""


def _attr(node, sel, base_url):
    s, attr = (sel.split("@", 1) + [""])[:2] if "@" in sel else (sel, "")
    el = node.select_one(s)
    if not el:
        return ""
    v = el.get(attr, "") if attr else el.get_text(" ", strip=True)
    return urljoin(base_url, v) if attr == "href" and v else v


def parse_results(html, base_url, source_id, source_name, selectors, region="Москва"):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for card in soup.select(selectors["card"]):
        title = _txt(card, selectors["title"])
        if not title:
            continue
        url = _attr(card, selectors["link"], base_url) or base_url
        full = card.get_text(" ", strip=True)
        m = _NUM_RE.search(url) or _NUM_RE.search(full)
        key = m.group(1) if m else url
        out.append(RawOrder(
            source_id=source_id, source_name=source_name, external_key=key,
            title=title[:500], description=full[:2000],
            quantity=parse_quantity(full), price=_txt(card, selectors["price"]),
            region=region, url=url,
        ))
    return out


class MosPortalCollector(BaseCollector):
    type = "mos_portal"

    def collect(self):
        selectors = {**DEFAULT_SELECTORS, **(self.cfg.get("selectors") or {})}
        queries = self.cfg.get("queries", ["пошив"])
        query_param = self.cfg.get("query_param", "query")
        region = self.cfg.get("region", "Москва")
        render_js = self.cfg.get("render_js", True)
        use_proxy = self.cfg.get("use_proxy", True)
        base = self.cfg.get("url", BASE)

        urls = [f"{base}?{urlencode({query_param: q})}" for q in queries]
        results, seen = [], set()

        def process(html_getter):
            for url in urls:
                try:
                    html = html_getter(url)
                except Exception as e:
                    log.error("[mos] %s: %s", url[:80], e)
                    continue
                for o in parse_results(html, base, self.source_id, self.source_name, selectors, region):
                    if o.external_key in seen:
                        continue
                    seen.add(o.external_key)
                    results.append(o)

        if render_js:
            try:
                from playwright.sync_api import sync_playwright
            except ImportError:
                log.warning("[mos] Playwright не установлен")
                return []
            proxy = settings.playwright_proxy() if use_proxy else None
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, proxy=proxy)
                page = browser.new_page(user_agent=USER_AGENT, locale="ru-RU", ignore_https_errors=True)
                try:
                    def g(url):
                        page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        try:
                            page.wait_for_selector(selectors["card"], timeout=15000)
                        except Exception:
                            pass
                        return page.content()
                    process(g)
                finally:
                    browser.close()
        else:
            import httpx
            proxy = settings.httpx_proxy() if use_proxy else None
            with httpx.Client(timeout=45, follow_redirects=True,
                              headers={"User-Agent": USER_AGENT}, proxy=proxy) as c:
                def g(url):
                    r = c.get(url); r.raise_for_status(); return r.text
                process(g)

        log.info("[mos] распознано лотов: %d", len(results))
        return results
