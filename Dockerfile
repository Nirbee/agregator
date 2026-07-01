# Образ с Python + Playwright/Chromium (для обхода WAF zakupki.gov.ru).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY requirements.txt .
# Базовые зависимости + опциональные (playwright для zakupki; zeep — ЕИС; telethon — Telegram)
RUN pip install --no-cache-dir -r requirements.txt playwright zeep telethon \
    && playwright install --with-deps chromium

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
