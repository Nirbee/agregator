"""Встроенный планировщик автосбора (APScheduler).

Запуск:  python -m app.scheduler
Собирает заказы каждые COLLECT_INTERVAL_MINUTES минут.
Альтернатива для продакшена — cron/systemd timer (см. deploy/).
"""
from __future__ import annotations

import logging
import time

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.collect_service import run_collection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("scheduler")


def main() -> None:
    interval = settings.collect_interval_minutes
    log.info("Планировщик запущен. Интервал: %d мин.", interval)

    # первый запуск сразу
    run_collection()

    sched = BackgroundScheduler(timezone="Europe/Moscow")
    sched.add_job(run_collection, "interval", minutes=interval, id="collect", max_instances=1)
    sched.start()

    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        sched.shutdown()
        log.info("Планировщик остановлен.")


if __name__ == "__main__":
    main()
