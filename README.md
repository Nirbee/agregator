# Агрегатор заказов на пошив

Внутренняя система для отдела продаж швейного производства: автоматически собирает
тендеры и частные заказы на пошив текстиля с разных площадок, фильтрует по заданным
параметрам и показывает их красивыми карточками на веб-портале — со ссылками и контактами.

## Что умеет

- Автосбор по расписанию (встроенный планировщик или systemd/cron).
- Фильтрация по типу (пошив/текстиль), минимальному объёму (от 50 шт) и географии — всё в `config.yaml`, без правки кода.
- Дедупликация: один и тот же заказ не задваивается.
- Веб-портал с карточками, поиском, фильтром по источнику, пометкой «просмотрено» и архивом.
- Basic-Auth для доступа отдела продаж (2–5 человек).

## Источники

| Источник | Тип | Статус | Что нужно для включения |
|---|---|---|---|
| Пошив.рус | парсинг HTML | ✅ готов | ничего (при JS-рендере — Playwright) |
| Швейник.онлайн | парсинг HTML | ✅ готов | то же |
| ЕИС zakupki.gov.ru (44/223-ФЗ) | SOAP API | ⚙️ каркас | `EIS_TOKEN` из личного кабинета ЕИС |
| Telegram (@poshivrus и др.) | Telethon | ⚙️ каркас | `TG_API_ID` / `TG_API_HASH` |
| Сбер-АСТ, Росэлторг, Фабрикант, порталы Москвы/МО | ЭТП | 🔲 заглушки | доступ/API каждой площадки |

> Швейные сайты client-rendered (контент грузится JS). Поставьте Playwright
> (`pip install playwright && playwright install chromium`) — в `config.yaml` уже стоит `render_js: true`.
> CSS-селекторы карточек проверьте в DevTools браузера и при необходимости поправьте в `config.yaml`.

## Быстрый старт (локально)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                 # заполните доступы/пароль портала

python -m scripts.seed_demo                          # демо-данные (по желанию)
uvicorn app.main:app --reload                        # портал на http://localhost:8000
```

Автосбор в отдельном окне:

```bash
python -m app.scheduler        # собирает каждые COLLECT_INTERVAL_MINUTES минут
# или разово:
python -m app.collect_service
```

## Продакшен на VPS (Linux)

Вариант A — Docker (проще всего):

```bash
cp .env.example .env      # заполнить
docker compose up -d      # поднимет web + scheduler
```

Вариант B — systemd (портал + таймер автосбора):

```bash
# код в /opt/agregator, venv в /opt/agregator/.venv
sudo cp deploy/agregator-web.service /etc/systemd/system/
sudo cp deploy/agregator-collect.* /etc/systemd/system/
sudo systemctl enable --now agregator-web
sudo systemctl enable --now agregator-collect.timer
systemctl list-timers | grep agregator     # проверить расписание
```

Расписание меняется в `deploy/agregator-collect.timer` (`OnUnitActiveSec=1h`)
или переменной `COLLECT_INTERVAL_MINUTES` для встроенного планировщика.

## Настройка фильтров

Всё в `config.yaml` → секция `filters`: `min_quantity`, `regions`, `include_keywords`,
`exclude_keywords`. Источники включаются/выключаются флагом `enabled`.

## Как подключить закрытые источники

1. **ЕИС** — получите индивидуальный токен в личном кабинете ЕИС (Настройки → Токены),
   впишите в `EIS_TOKEN`, поставьте `enabled: true` у источника `eis`.
   Каркас SOAP-запроса и точки входа — в `app/collectors/eis_collector.py` (адаптируйте под актуальный WSDL).
2. **Telegram** — получите `api_id`/`api_hash` на https://my.telegram.org, впишите в `.env`,
   один раз авторизуйтесь (создастся файл сессии), включите источник `telegram`.
3. **ЭТП** — под каждую площадку реализуйте доступ в `app/collectors/etp_collector.py`
   (открытый поиск, API по договору или парсинг через Playwright).

## Структура

```
app/
  main.py            — веб-портал (FastAPI)
  collect_service.py — цикл сбора: источники → фильтр → дедуп → БД
  scheduler.py       — встроенный планировщик
  filters.py         — движок фильтрации + разбор количества
  models.py          — модель заказа (SQLAlchemy)
  config.py          — загрузка .env и config.yaml
  collectors/        — коллекторы источников (html/eis/telegram/etp)
  templates/, static/— портал с карточками
config.yaml          — фильтры и источники
deploy/              — systemd unit'ы
Dockerfile, docker-compose.yml
```

## Правовая заметка

Парсинг сайтов ведите с учётом их правил использования и robots.txt; для ЭТП/ЕИС
предпочтителен официальный API. Персональные данные и контакты из заказов используйте
только в рамках закона.

---

## Развёртывание на сервере (VPS в России, через Docker)

Сервер должен быть в РФ — иначе zakupki.gov.ru и ЕИС могут быть недоступны/медленны.

### Требуемые характеристики VPS

Из-за Playwright/Chromium (нужен для обхода WAF zakupki.gov.ru) память — главный ресурс.

| Параметр | Минимум | Рекомендуется |
|---|---|---|
| CPU | 2 vCPU | 2–4 vCPU |
| RAM | 2 ГБ | 4 ГБ |
| Диск | 20 ГБ SSD | 40 ГБ SSD (образ с Chromium ~1.5 ГБ + база) |
| ОС | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS |
| Сеть | локация РФ | локация РФ, безлимит |

Подойдут Timeweb, Selectel, VDSina, Reg.ru, Rusonyx и т.п. Для 2–5 пользователей
и периодического сбора этого достаточно; при `regions_codes: ["all"]` для ЕИС и
частом сборе лучше 4 ГБ RAM.

### Установка одной командой

```bash
git clone https://github.com/Nirbee/agregator.git
cd agregator
sudo bash deploy/install.sh          # поставит Docker и создаст .env
nano .env                            # задайте PORTAL_PASSWORD (и токены при необходимости)
sudo bash deploy/update.sh           # соберёт образ и запустит
```

Портал: `http://<IP-сервера>:8000` (логин/пароль из `.env`).

### Обновление после изменений

```bash
cd agregator && sudo bash deploy/update.sh
```

### Полезные команды

```bash
docker compose ps                    # статус контейнеров
docker compose logs -f scheduler     # логи автосбора
docker compose logs -f web           # логи портала
docker compose restart               # перезапуск
docker compose down                  # остановить
```

Автосбор выполняет контейнер `scheduler` каждые `COLLECT_INTERVAL_MINUTES` минут
(по умолчанию 60), задаётся в `.env`. Данные хранятся в `./data` (том Docker),
конфигурация фильтров/источников — в `config.yaml` (правится на сервере, применяется
после `docker compose restart`).

### Безопасность (рекомендуется)

Портал защищён Basic-Auth, но лучше не открывать порт 8000 всему интернету:
поставьте перед ним Nginx с HTTPS (Let's Encrypt) и/или ограничьте доступ по IP
через firewall (`ufw allow from <ваш-IP> to any port 8000`).
