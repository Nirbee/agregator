"""Заполняет БД демо-заказами, чтобы сразу увидеть портал.

Запуск:  python -m scripts.seed_demo
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import Order, SessionLocal, init_db, make_fingerprint  # noqa: E402

DEMO = [
    dict(source_id="eis", source_name="ЕИС zakupki.gov.ru", title="Пошив футболок с логотипом для нужд учреждения",
         description="Требуется пошив хлопковых футболок 100% cotton, плотность 160 г/м². Нанесение логотипа шелкографией.",
         quantity=1500, price="НМЦК 1 850 000 ₽", region="Москва", customer="ГБУ «Спортивный центр»",
         url="https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=0173200001425000123",
         contact="+7 (495) 000-00-00, zakupki@example.ru",
         deadline_at=datetime.utcnow() + timedelta(days=6)),
    dict(source_id="poshivrus", source_name="Пошив.рус", title="Свитшоты оверсайз, партия 300 шт",
         description="Ищу производство для пошива свитшотов оверсайз, футер 3-нитка с начёсом. Размеры S-XXL.",
         quantity=300, region="Санкт-Петербург", customer="Бренд одежды",
         url="https://xn--b1agjdgq7e.xn--80asehdb/Orders/12345", contact="@brand_manager, +7 900 111-22-33",
         deadline_at=datetime.utcnow() + timedelta(days=14)),
    dict(source_id="poshivrus", source_name="Пошив.рус", title="Лонгсливы под нанесение, 500 штук",
         description="Нужны лонгсливы белые и чёрные, кулирка 100% хлопок. Регулярный заказ раз в месяц.",
         quantity=500, region="Казань", url="https://xn--b1agjdgq7e.xn--80asehdb/Orders/12346",
         contact="ivan@merchbrand.ru"),
    dict(source_id="telegram", source_name="Telegram @poshivrus", title="Постельное бельё, комплекты 200 шт",
         description="Ищем швейный цех: постельное бельё 1.5-спальное, бязь. Ткань наша.",
         quantity=200, region="Иваново", url="https://t.me/poshivrus/9876", contact="@textile_opt",
         published_at=datetime.utcnow() - timedelta(hours=3)),
    dict(source_id="eis", source_name="ЕИС zakupki.gov.ru", title="Поставка махровых полотенец для санатория",
         description="Полотенца махровые 70x140, 500 г/м², белые. Поставка с логотипом.",
         quantity=800, price="НМЦК 640 000 ₽", region="Краснодарский край", customer="ФГБУ Санаторий",
         url="https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=0318300000000000456",
         contact="tender@sanatoriy.ru", deadline_at=datetime.utcnow() + timedelta(days=9)),
    dict(source_id="shveinik", source_name="Швейник.онлайн", title="Спецодежда: куртки рабочие, 250 шт",
         description="Ищу производителя спецодежды: куртки утеплённые, ткань оксфорд, светоотражающие полосы.",
         quantity=250, region="Екатеринбург", url="https://xn--b1alrd0c.xn--p1acf/ads/12", contact="+7 912 345-67-89"),
]


def main() -> None:
    init_db()
    session = SessionLocal()
    added = 0
    try:
        for i, d in enumerate(DEMO):
            fp = make_fingerprint(d["source_id"], d.get("url") or f"demo-{i}")
            if session.query(Order).filter_by(fingerprint=fp).first():
                continue
            session.add(Order(fingerprint=fp, is_new=True, **d))
            added += 1
        session.commit()
    finally:
        session.close()
    print(f"Добавлено демо-заказов: {added}")


if __name__ == "__main__":
    main()
