# koloGo — агентские соглашения

## О проекте
Telegram-бот на aiogram для менеджмента платных поездок из колледжа в Минск.
Водитель (один админ) создаёт поездки, пассажиры бронируют места
(количество задаётся при создании, по умолчанию 4),
платят с депозита, который админ пополняет вручную (нал, без платёжных шлюзов).

## Стек (взято из репозитория Tunnex — эталонный гайдлайн)
- Python 3.13+, aiogram 3 + aiogram-dialog 2
- dishka (DI), adaptix (dataclass-схемы), SQLAlchemy 2 + asyncpg + alembic
- Redis (FSM + кэш), apscheduler, orjson
- ruff / isort / mypy / pyright, Justfile, uv

## Архитектура (DDD-слои в `src/kologo`)
- `domain/` — чистые dataclass-схемы сущностей и исключения, без зависимостей.
- `application/` — сервисы (cross-cutting) и интеракторы (use-case) с командами и фасадами.
- `infrastructure/` — конфиг, БД (models + dao), кэш, логирование, уведомления, шедулер, DI (`ioc.py`).
- `presentation/` — роутеры, middleware, aiogram-dialog окна (user_dialogs / admin_dialogs).

## Конвенции
- DAO маппит ORM → domain-dataclass через `_map_to_domain`.
- Сессия БД открывается в dishka-провайдере с `session.begin()` (транзакция на запрос).
- Все строки UI — на русском, встроены в диалоги напрямую (bot только русский).
- Числа денег — `Decimal` в БД (`Numeric(10,2)`), `float` в domain-схемах.
- Кэш-ключи — типобезопасные `CacheKey[CacheValue]` в `infrastructure/cache/keys.py`.
- `PostCommit` (request scope): `BotService.notify_user`/`send_log_to_admin` и повторный `RedisService.delete` выполняются только после коммита транзакции запроса. Если нужен результат отправки сразу (счётчик доставок) — `notify_user_now`.
- Баланс меняется только через `UsersDAO.increase_balance`/`decrease_balance` (SELECT … FOR UPDATE).
- Константы, лимиты, тексты-справочники и маппинги статусов — только в `AppConfig` (`infrastructure/config/app.py`), инжектится через dishka (`FromDishka[AppConfig]`). Модульных глобальных констант нет.
- Без докстрингов. Без `except Exception`/`BaseException` — ловить только конкретные исключения.
- Тестовые прогоны на локальной БД — только в транзакции с откатом; шедулерные джобы на реальной БД не запускать.
- Кэш — cache-aside в сервисах (`get` → DAO → `set`), сериализация домена в `cache/serializers.py`; при любой мутации, затрагивающей закэшированные данные, сервис обязан вызвать инвалидацию (`delete`). Чтение кэшированных списков/статов — только через методы сервисов (`RideService.get_upcoming_rides`, `get_ride_stats`, `list_pending_bookings`, `next_active_booking`, `user_booking_counts`, `list_templates`, `list_active_rides`, `get_in_progress_ride`, `LocationService.list_all`), а не напрямую из DAO — иначе кэш обходится.

## Команды
- `just install-dev` — установить зависимости
- `just migrate` — применить миграции
- `just migrate-new "сообщение"` — новая автоген-миграция
- `just run` / `just watch` — запуск / запуск с авто-перезагрузкой
- `just lint` / `just format` / `just typecheck` — проверки

## Доменная модель
- **User**: пассажир. Поля: `balance` (депозит), `is_banned` (ЧС), `is_vip` (бесплатно + авто-апрув), `is_admin` (водитель).
- **Ride**: поездка. `departure_at`, `origin`/`destination` (маршрут, NOT NULL; координаты `*_lat`/`*_lon` опциональны), `price` (0 = бесплатная), `seats_total` (задаётся при создании), `is_visible` (публикация), `auto_approve`, `status` (open/closed/in_progress/completed/cancelled). Трекинг: `started_at`, `finished_at`, `track_distance_m`, live-поля в ORM.
- **Location**: именованная гео-точка для маршрутов (название + lat/lon), управляется через Настройки.
- **RideTrackPoint**: точка трека поездки (seq + lat/lon), пишется во время live-гео трекинга.
- **Booking**: бронь 1 места. `status` (pending/approved/rejected/cancelled/completed/no_show), `paid_amount` (сколько списано с депозита).
- **Transaction**: движение депозита. `type` (admin_topup/admin_decrease/ride_payment/refund), `amount`, `ride_id?`.

## Бизнес-правила (edge cases)
- VIP: поездка бесплатна (paid_amount=0) + всегда авто-апрув, даже если ride.auto_approve=False.
- Бесплатная поездка (price=0): никто не платит, апрув по ride.auto_approve / VIP.
- Платная поездка: списание с баланса при бронировании; при reject/cancel — возврат.
- Бронь невозможна: нет свободных мест (считаются только approved), поездка закрыта/невидима/в прошлом, пользователь в ЧС, уже забронировано, водитель уже отклонил бронь на эту поездку.
- Заявок (pending) может быть больше, чем мест. Апрув невозможен, если approved == seats_total (NoFreeSeatsError); как только места заполнены — оставшиеся pending автоматически отменяются с уведомлением «все места заняты» (статус cancelled, чтобы можно было подать снова, если место освободится).
- Поездку нельзя создать/перенести в прошлое (RideInPastError).
- Сессия БД с autoflush=False: DAO-сеттеры, после которых идут count/select-запросы, обязаны делать flush.
- Скрытая поездка (`is_visible=False`): не видна в списке для тех, кто не забронировал; забронировавшие видят свою бронь.
- Отмена поездки админом → возврат всем + уведомление.
- No-show: админ отмечает, возврата нет, в статистику не идёт как completed.
- Трекинг поездки: админ жмёт «Старт поездки» → шлёт live-гео → статус `in_progress`, точки в `ride_track_points`; прибытие — отрезок между апдейтами прошёл в `arrival_radius_m` (150м) от точки прибытия `arrival_debounce` (2) раза подряд → авто-завершение; также авто-завершение, если стоп live-гео в радиусе или в радиусе нет новых точек `arrival_dwell_s` (60с, джоба `finish_stale_arrivals`). Без координат точки прибытия автозавершения нет. Одно сообщение пассажирам со статой (выезд/прибытие/время/дистанция/скорости) + кнопка маршрута Яндекс. Стоп live-гео вне радиуса → трекинг снимается, поездка завершается вручную.
- Незавершённые поездки: OPEN через 30 мин после выезда → CLOSED + админу «не стартовала» с кнопкой «🏁 Завершить»; CLOSED/IN_PROGRESS через `auto_complete_after_h` (12 ч) после выезда → автоматический `complete_ride` (джоба `auto_complete_stale_rides`).
- CryptoBot: инвойс создаётся с `expires_in` 15 мин; `PaymentService.process_cryptobot_invoice` сначала проверяет оплату, потом истечение; отмена удаляет инвойс в CryptoBot; при старте бота опрос ожидающих инвойсов восстанавливается. Stars: обязателен ответ на `pre_checkout_query`; `transactions.payment_id` уникален.
- Health-check: `infrastructure/health.py` (aiohttp), `GET /health` → `200 OK`. Хост/порт/путь — секция `[health]` в `config.toml` (по умолчанию `0.0.0.0:8080/health`). Сервер поднимается через `HealthProvider` (APP scope) и гасится на `container.close()`.
