"""Универсальный HTML-коллектор для швейных площадок.

Работает по CSS-селекторам из config.yaml. Два режима:
  - обычный HTTP-запрос (httpx) для серверного рендеринга;
  - render_js=true — рендеринг через Playwright (headless) для
    client-rendered сайтов (пошив.рус, швейник.онлайн).
Селектор вида "a@href" = взять атрибут href у элемента a.
"""
from __future__ import annotations

import logging
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.collectors.base import BaseCollector
from app.filters import RawOrder, parse_quantity

log = logging.getLogger("collector.html")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)


def _extract(node, selector, base_url=""):
    if not selector:
        return ""
    attr = None
    if "@" in selector:
        selector, attr = selector.rsplit("@", 1)
    el = node.select_one(selector)
    if el is None:
        return ""
    if attr:
        val = el.get(attr, "")
        if attr == "href" and val:
            return urljoin(base_url, val)
        return val
    return el.get_text(" ", strip=True)


class HtmlCollector(BaseCollector):
    type = "html"

    def _fetch_html(self):
        url = self.cfg["url"]
        cookie = self.cfg.get("cookie", "")
        headers = {"User-Agent": USER_AGENT}
        if cookie:
            headers["Cookie"] = cookie

        if self.cfg.get("render_js"):
            return self._fetch_rendered(url, headers)

        with httpx.Client(timeout=30, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.text

    def _fetch_rendered(self, url, headers):
        """Рендеринг JS через Playwright. Нужно: pip install playwright && playwright install chromium."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            log.warning("[%s] render_js=true, но Playwright не установлен "
                        "(pip install playwright && playwright install chromium)", self.source_id)
            return ""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=headers["User-Agent"])
            page.goto(url, wait_until="networkidle", timeout=60000)
            html = page.content()
            browser.close()
            return html

    def collect(self):
        sel = self.cfg.get("selectors", {})
        base_url = self.cfg["url"]
        try:
            html = self._fetch_html()
        except Exception as e:
            log.error("[%s] ошибка загрузки: %s", self.source_id, e)
            return []
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(sel.get("card", "")) if sel.get("card") else []
        results = []

        for card in cards:
            title = _extract(card, sel.get("title", ""))
            if not title:
                continue
            desc = _extract(card, sel.get("description", ""))
            qty_text = _extract(card, sel.get("quantity", ""))
            quantity = parse_quantity(qty_text) or parse_quantity(f"{title} {desc}")
            url = _extract(card, sel.get("link", ""), base_url) or base_url

            results.append(
                RawOrder(
                    source_id=self.source_id,
                    source_name=self.source_name,
                    external_key=url or title,
                    title=title,
                    description=desc,
                    quantity=quantity,
                    region=_extract(card, sel.get("region", "")),
                    url=url,
                    contact=_extract(card, sel.get("contact", "")),
                )
            )

        log.info("[%s] найдено карточек: %d", self.source_id, len(results))
        return results
