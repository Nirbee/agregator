"""Коллектор госзакупок через ПУБЛИЧНЫЙ поиск zakupki.gov.ru — без токена.

zakupki.gov.ru блокирует многие IP дата-центров/хостингов. Запросы можно пускать
через российский прокси (PROXY_URL в .env). Страница по умолчанию забирается
настоящим браузером (Playwright, render_js: true) для обхода WAF; есть httpx-режим.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

from app.collectors.base import BaseCollector
from app.config import settings
from app.filters import RawOrder, parse_quantity

log = logging.getLogger("collector.zakupki")

BASE = "https://zakupki.gov.ru/epz/order/extendedsearch/results.html"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

DEFAULT_SELECTORS = {
    "card": "div.search-registry-entry-block",
    "number_link": ".registry-entry__header-mid__number a",
    "object": ".registry-entry__body-value",
    "customer": ".registry-entry__body-href",
    "price": ".price-block__value",
}

_REG_RE = re.compile(r"(\d{11,})")
_DATE_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")


def _txt(node, sel):
    el = node.select_one(sel)
    return el.get_text(" ", strip=True) if el else ""


def _parse_date(text):
    """Первая дата dd.mm.yyyy из текста -> datetime (или None)."""
    m = _DATE_RE.search(text or "")
    if not m:
        return None
    d, mth, y = (int(x) for x in m.groups())
    try:
        return dt.datetime(y, mth, d)
    except ValueError:
        return None


def parse_results(html, base_url, source_id, source_name, selectors):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for card in soup.select(selectors["card"]):
        link_el = card.select_one(selectors["number_link"])
        title = _txt(card, selectors["object"])
        href = link_el.get("href", "") if link_el else ""
        url = urljoin(base_url, href) if href else ""
        num_text = link_el.get_text(" ", strip=True) if link_el else ""
        m = _REG_RE.search(num_text) or _REG_RE.search(href)
        reg = m.group(1) if m else (num_text or href)

        if not title:
            title = num_text or "Закупка"

        full_text = card.get_text(" ", strip=True)
        # даты: первая на карточке = размещение; берём максимум как срок (грубая эвристика)
        dates = [_parse_date(mo.group(0)) for mo in _DATE_RE.finditer(full_text)]
        dates = [x for x in dates if x]
        published_at = dates[0] if dates else None
        deadline_at = max(dates) if len(dates) > 1 else None

        out.append(
            RawOrder(
                source_id=source_id,
                source_name=source_name,
                external_key=reg or url or title,
                title=title[:500],
                description=full_text[:2000],
                quantity=parse_quantity(full_text),
                price=_txt(card, selectors["price"]),
                customer=_txt(card, selectors["customer"]),
                url=url or base_url,
                published_at=published_at,
                deadline_at=deadline_at,
            )
        )
    return out


class ZakupkiSearchCollector(BaseCollector):
    type = "zakupki_search"

    def _use_proxy(self):
        return self.cfg.get("use_proxy", True)

    def collect(self):
        selectors = {**DEFAULT_SELECTORS, **(self.cfg.get("selectors") or {})}
        queries = self.cfg.get("queries", ["пошив"])
        pages = int(self.cfg.get("pages", 1))
        records = self.cfg.get("records_per_page", "_50")
        render_js = self.cfg.get("render_js", True)

        base_params = {
            "morphology": "on",
            "sortBy": "UPDATE_DATE",
            "sortDirection": "false",
            "recordsPerPage": records,
            "af": "on",
        }
        if self.cfg.get("fz44", True):
            base_params["fz44"] = "on"
        if self.cfg.get("fz223", True):
            base_params["fz223"] = "on"

        urls = []
        for q in queries:
            for page in range(1, pages + 1):
                params = dict(base_params, searchString=q, pageNumber=page)
                urls.append((q, page, f"{BASE}?{urlencode(params)}"))

        if render_js:
            return self._collect_rendered(urls, selectors)
        return self._collect_httpx(urls, selectors)

    def _finish(self, pairs, selectors, html_getter):
        results = []
        seen = set()
        for q, page, url in pairs:
            try:
                html = html_getter(url)
            except Exception as e:
                log.error("[zakupki] запрос '%s' стр.%d: %s", q, page, e)
                continue
            if not html:
                continue
            for order in parse_results(html, BASE, self.source_id, self.source_name, selectors):
                if order.external_key in seen:
                    continue
                seen.add(order.external_key)
                results.append(order)
        log.info("[zakupki] распознано закупок: %d", len(results))
        return results

    def _collect_httpx(self, urls, selectors):
        import httpx
        headers = {"User-Agent": USER_AGENT, "Accept-Language": "ru-RU,ru;q=0.9"}
        proxy = settings.httpx_proxy() if self._use_proxy() else None
        if proxy:
            log.info("[zakupki] httpx через прокси")
        with httpx.Client(timeout=45, follow_redirects=True, headers=headers, proxy=proxy) as client:
            def getter(url):
                r = client.get(url)
                r.raise_for_status()
                return r.text
            return self._finish(urls, selectors, getter)

    def _collect_rendered(self, urls, selectors):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            log.warning("[zakupki] render_js=true, но Playwright не установлен "
                        "(pip install playwright && playwright install chromium)")
            return []
        card_sel = selectors["card"]
        proxy = settings.playwright_proxy() if self._use_proxy() else None
        if proxy:
            log.info("[zakupki] браузер через прокси %s", proxy.get("server"))
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, proxy=proxy)
            page = browser.new_page(user_agent=USER_AGENT, locale="ru-RU", ignore_https_errors=True)

            def getter(url):
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                try:
                    page.wait_for_selector(card_sel, timeout=15000)
                except Exception:
                    pass
                return page.content()

            try:
                return self._finish(urls, selectors, getter)
            finally:
                browser.close()
