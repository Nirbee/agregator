# Интеграция AI-фильтра (Claw) с агрегатором

Claw — второй уровень фильтрации: читает уже собранные карточки, оценивает их
0–100 по привлекательности «реального заказа на пошив» и пишет оценку обратно.
Портал показывает бейдж рейтинга, умеет сортировать по нему и фильтровать «от N».

## 1. Где данные

SQLite: `data/agregator.db` (на сервере — `/root/agregator/data/agregator.db`).
Включён режим **WAL**, так что читать/писать можно параллельно с приложением.
В своём подключении обязательно выстави:

```sql
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
```

## 2. Схема (таблица `orders`, важные поля)

| поле | тип | смысл |
|---|---|---|
| `id` | int | PK |
| `source_id` | text | `zakupki_search` / `eis` / `zakupki_mos` / `poshivrus` / `telegram` … |
| `title` | text | предмет закупки / заголовок |
| `description` | text | полный текст карточки |
| `quantity` | int/null | тираж, шт (если распознан) |
| `price` | text | НМЦК/бюджет (для тендеров) |
| `region` | text | регион |
| `customer` | text | заказчик |
| `url` | text | ссылка на заказ |
| `contact` | text | контакт (для частных/Telegram) |
| `published_at` / `deadline_at` | datetime/null | даты |
| **`ai_rating`** | int/null | **пишет Claw**: 0..100; NULL = не оценён |
| **`ai_reason`** | text | **пишет Claw**: краткое обоснование (≤400 симв.) |
| **`ai_analyzed_at`** | datetime | **пишет Claw**: время оценки |

## 3. Что читать / что писать

Брать только НЕоценённые (не жечь токены повторно):

```sql
SELECT id, source_id, title, description, quantity, price, region, customer, contact
FROM orders
WHERE ai_rating IS NULL AND is_archived = 0
ORDER BY collected_at DESC
LIMIT 100;
```

Записать оценку:

```sql
UPDATE orders
SET ai_rating = :rating, ai_reason = :reason, ai_analyzed_at = CURRENT_TIMESTAMP
WHERE id = :id;
```

Пересмотреть старые оценки (по желанию) — просто выставить им `ai_rating = NULL`.

## 4. Рекомендованный промпт (различает тендер и частника)

> Ты оцениваешь заявку для швейного производства. Верни СТРОГО JSON:
> `{"rating": <0-100>, "reason": "<до 30 слов>"}`.
>
> Критерии:
> - Это реальный ЗАКАЗ НА ПОШИВ/ПРОИЗВОДСТВО, а не поставка готового/перепродажа/ремонт?
> - Если `source_id` = zakupki_search/zakupki_mos/eis — это ГОСЗАКУПКА: сигналы качества —
>   указан НМЦК/price, конкретный предмет, ОКПД2/ТЗ, адекватный срок подачи.
> - Если частник (poshivrus/telegram/…): сигналы — «ищу производство», конкретная ткань
>   (футер, кулирка, плотность), наличие лекал/ТЗ, тираж ≥100, есть контакт.
> - Гео: Москва/МО — плюс (но НЕ жёсткий отсев: вся Россия допустима, дальний регион −10–15).
> - Минусы: «поставка готового», «перепродажа», «ищу дёшево в Китае», нет конкретики, нет контактов.
>
> Данные заявки:
> source_id: {source_id}
> title: {title}
> quantity: {quantity} | price: {price} | region: {region}
> description: {description[:1500]}

Разбирай ответ как JSON; при сбое парсинга — пропусти запись (не пиши мусор).

## 5. Как показывается в портале

- Бейдж `AI N` в карточке (зелёный ≥80, оранжевый 60–79, серый <60), при наведении — reason.
- Сортировка: «По AI-рейтингу».
- Фильтр: «AI ≥ 40 / 60 / 80».
- Счётчик «с оценкой» в шапке.

## 6. Автоматизация

Готовый каркас: `scripts/ai_score.py` (сейчас с эвристикой-заглушкой). Claw заменяет
функцию `score_order()` вызовом своей модели по промпту выше. Запуск по расписанию —
рядом со сбором (cron/таймер), например каждые 15 минут:

```
*/15 * * * * cd /root/agregator && .venv/bin/python -m scripts.ai_score >> /var/log/ai_score.log 2>&1
```

Порог показа настраивается в портале (min_rating), а не в БД — сырые оценки сохраняются все.

---

## 7. HTTP API (рекомендованный способ записи от Claw)

Вместо прямого доступа к SQLite Claw работает по HTTP. Включается ключом `API_KEY`
в `.env` (придумайте длинную случайную строку). Все запросы — с заголовком
`X-API-Key: <ваш ключ>`. Базовый адрес: `http://<IP-сервера>:8000`.

### Взять неоценённые карточки
```
GET /api/orders/unscored?limit=100
X-API-Key: <ключ>
```
Ответ — JSON-массив:
```json
[{"id":318,"source_id":"zakupki_search","title":"...","description":"...",
  "quantity":1000,"price":"НМЦК ...","region":"Москва","customer":"...",
  "contact":"","url":"https://zakupki.gov.ru/..."}]
```

### Записать оценки (пачкой)
```
POST /api/orders/rate
X-API-Key: <ключ>
Content-Type: application/json

[{"id":318,"rating":85,"reason":"Явный пошив, есть ТЗ, Москва"},
 {"id":319,"rating":15,"reason":"Поставка готового, не пошив"}]
```
Ответ: `{"updated": 2}`.

### Пример на Python (сторона Claw)
```python
import httpx
H = {"X-API-Key": "<ключ>"}
base = "http://<IP>:8000"
orders = httpx.get(f"{base}/api/orders/unscored", headers=H, timeout=30).json()
results = []
for o in orders:
    rating, reason = claw_score(o)     # ваш вызов модели по промпту из п.4
    results.append({"id": o["id"], "rating": rating, "reason": reason})
httpx.post(f"{base}/api/orders/rate", json=results, headers=H, timeout=60)
```

Оценки сразу видны на странице **/ai** (сортировка по баллу, лучшие сверху).
Кнопка «Оценить новые» на /ai запускает встроенную эвристику (заглушку) — на время,
пока Claw не подключён.
