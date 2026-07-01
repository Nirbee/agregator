"""Коллектор ЕИС zakupki.gov.ru (44-ФЗ) через сервис отдачи информации getDocsIP.

Схема: POST getDocsByOrgRegionRequest (токен в SOAP-заголовке individualPerson_token)
-> в ответе ссылка на ZIP-архив (archiveUrl) -> архив качается GET-запросом с токеном
в HTTP-заголовке individualPerson_token -> XML-извещения разбираются -> фильтруются.
Токен: ЛК ЕИС -> Администрирование -> Настройка выдачи идентификатора для сервисов отдачи.
Доступ к int44.zakupki.gov.ru может требовать российского прокси (PROXY_URL в .env).
"""
from __future__ import annotations

import datetime as dt
import io
import logging
import uuid
import xml.etree.ElementTree as ET
import zipfile

import httpx

from app.collectors.base import BaseCollector
from app.config import settings
from app.filters import RawOrder, parse_quantity

log = logging.getLogger("collector.eis")

DEFAULT_SERVICE_URL = "https://int44.zakupki.gov.ru/eis-integration/services/getDocsIP"
DEFAULT_NS = "http://zakupki.gov.ru/fz44/get-docs-ip/ws"

ALL_REGION_CODES = [f"{i:02d}" for i in range(1, 93)]

REQUEST_TEMPLATE = (
    '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
    'xmlns:ws="{ns}">'
    "<soapenv:Header><individualPerson_token>{token}</individualPerson_token></soapenv:Header>"
    "<soapenv:Body><ws:getDocsByOrgRegionRequest>"
    "<index><id>{req_id}</id><createDateTime>{created}</createDateTime><mode>PROD</mode></index>"
    "<selectionParams>"
    "<orgRegion>{region}</orgRegion>"
    "<subsystemType>{subsystem}</subsystemType>"
    "<documentType44>{doc_type}</documentType44>"
    "<periodInfo><exactDate>{exact_date}</exactDate></periodInfo>"
    "</selectionParams>"
    "</ws:getDocsByOrgRegionRequest></soapenv:Body></soapenv:Envelope>"
)


def _localname(tag):
    return tag.rsplit("}", 1)[-1]


def _find_archive_url(xml_bytes):
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return ""
    for el in root.iter():
        if _localname(el.tag) == "archiveUrl" and (el.text or "").strip():
            return el.text.strip()
    return ""


def _parse_notice(xml_bytes, source_id, source_name):
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None

    title = ""
    reg_number = ""
    price = ""
    customer = ""
    all_text = []

    for el in root.iter():
        ln = _localname(el.tag)
        txt = (el.text or "").strip()
        if not txt:
            continue
        all_text.append(txt)
        if ln == "purchaseObjectInfo" and not title:
            title = txt
        elif ln == "purchaseNumber" and not reg_number:
            reg_number = txt
        elif ln in ("maxPrice", "contractPrice") and not price:
            price = txt
        elif ln in ("fullName", "shortName") and not customer:
            customer = txt

    if not title:
        title = next((t for t in all_text if len(t) > 15), "")
    if not title:
        return None

    if reg_number:
        url = "https://zakupki.gov.ru/epz/order/extendedsearch/results.html?searchString=" + reg_number
    else:
        url = "https://zakupki.gov.ru/epz/order/extendedsearch/results.html"
    description = " | ".join(dict.fromkeys(all_text))[:2000]

    return RawOrder(
        source_id=source_id,
        source_name=source_name,
        external_key=reg_number or title,
        title=title[:500],
        description=description,
        quantity=parse_quantity(description),
        price=price,
        customer=customer,
        url=url,
    )


class EisCollector(BaseCollector):
    type = "eis_soap"

    def collect(self):
        token = settings.eis_token
        if not token:
            log.info("[eis] EIS_TOKEN не задан — коллектор пропущен.")
            return []

        service_url = self.cfg.get("service_url", DEFAULT_SERVICE_URL)
        ns = self.cfg.get("ws_namespace", DEFAULT_NS)
        subsystem = self.cfg.get("subsystem_type", "PRIZ")
        doc_types = self.cfg.get("document_types", ["epNotificationEF2020"])
        days_back = int(self.cfg.get("days_back", 1))

        regions = self.cfg.get("regions_codes", ["77"])
        if regions in (["all"], "all"):
            regions = ALL_REGION_CODES

        dates = [(dt.date.today() - dt.timedelta(days=d)).isoformat() for d in range(days_back)]

        proxy = settings.httpx_proxy() if self.cfg.get("use_proxy", True) else None
        if proxy:
            log.info("[eis] запросы через прокси")

        results = []
        seen_urls = set()

        with httpx.Client(timeout=60, follow_redirects=True, proxy=proxy) as client:
            for region in regions:
                for doc_type in doc_types:
                    for exact_date in dates:
                        try:
                            archive_url = self._request_archive(
                                client, service_url, ns, token,
                                region, subsystem, doc_type, exact_date,
                            )
                            if archive_url:
                                results.extend(
                                    self._download_and_parse(client, archive_url, token, seen_urls)
                                )
                        except Exception as e:
                            log.error("[eis] регион=%s тип=%s дата=%s: %s",
                                      region, doc_type, exact_date, e)

        log.info("[eis] распознано извещений: %d", len(results))
        return results

    def _request_archive(self, client, service_url, ns, token,
                         region, subsystem, doc_type, exact_date):
        xml = REQUEST_TEMPLATE.format(
            ns=ns, token=token, req_id=str(uuid.uuid4()),
            created=dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            region=region, subsystem=subsystem, doc_type=doc_type, exact_date=exact_date,
        )
        resp = client.post(
            service_url,
            content=xml.encode("utf-8"),
            headers={"Content-Type": "text/xml; charset=utf-8"},
        )
        resp.raise_for_status()
        return _find_archive_url(resp.content)

    def _download_and_parse(self, client, archive_url, token, seen_urls):
        resp = client.get(archive_url, headers={"individualPerson_token": token})
        resp.raise_for_status()

        out = []
        try:
            zf = zipfile.ZipFile(io.BytesIO(resp.content))
        except zipfile.BadZipFile:
            log.warning("[eis] ответ не является ZIP-архивом (%s)", archive_url[:80])
            return out

        for name in zf.namelist():
            if not name.lower().endswith(".xml"):
                continue
            order = _parse_notice(zf.read(name), self.source_id, self.source_name)
            if order and order.url not in seen_urls:
                seen_urls.add(order.url)
                out.append(order)
        return out
