from dataclasses import dataclass, field
from datetime import timedelta

from seatbot.domain.schemas import BookingStatus, RideStatus


@dataclass(frozen=True, slots=True)
class AppConfig:
    config_path: str = "secret_data/config.toml"
    logger_config_path: str = "secret_data/logger-config.json"
    bot_http_timeout_s: int = 30
    redis_max_connections: int = 5
    fsm_state_ttl_s: int = 9000
    fsm_data_ttl_s: int = 7200

    byn_to_usd_rate_key: str = "byn_to_usd_rate"
    byn_to_usd_rate_default: float = 3.2
    byn_to_stars_rate_key: str = "byn_to_stars_rate"
    byn_to_stars_rate_default: float = 1.0
    vip_price_key: str = "vip_price"
    vip_price_default: float = 100.0

    cryptobot_invoice_ttl: timedelta = timedelta(minutes=15)
    stars_payload_prefix: str = "stars_topup:"
    topup_min_byn: float = 1.0
    topup_max_byn: float = 1000.0

    max_ride_price: float = 10_000
    max_repeat_days: int = 28
    max_deposit_amount: float = 100_000
    earth_radius_m: float = 6_371_000

    active_ride_statuses: tuple[RideStatus, ...] = (
        RideStatus.OPEN,
        RideStatus.CLOSED,
        RideStatus.IN_PROGRESS,
    )

    weekdays_ru: tuple[str, ...] = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
    all_weekdays: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6)
    workdays: tuple[int, ...] = (0, 1, 2, 3, 4)

    booking_status_ru: dict[BookingStatus, str] = field(
        default_factory=lambda: {
            BookingStatus.PENDING: "ожидает",
            BookingStatus.APPROVED: "одобрена",
            BookingStatus.REJECTED: "отклонена",
            BookingStatus.CANCELLED: "отменена",
            BookingStatus.COMPLETED: "завершена",
            BookingStatus.NO_SHOW: "неявка",
        }
    )
    booking_status_emoji: dict[BookingStatus, str] = field(
        default_factory=lambda: {
            BookingStatus.PENDING: "⏳",
            BookingStatus.APPROVED: "✅",
            BookingStatus.REJECTED: "❌",
            BookingStatus.CANCELLED: "🚫",
            BookingStatus.COMPLETED: "🏁",
            BookingStatus.NO_SHOW: "🙅",
        }
    )
    ride_status_emoji: dict[RideStatus, str] = field(
        default_factory=lambda: {
            RideStatus.OPEN: "🟢",
            RideStatus.CLOSED: "🟡",
            RideStatus.IN_PROGRESS: "🚙",
            RideStatus.COMPLETED: "✅",
            RideStatus.CANCELLED: "❌",
        }
    )
    next_booking_status: dict[BookingStatus, str] = field(
        default_factory=lambda: {
            BookingStatus.APPROVED: "✅ Место закреплено",
            BookingStatus.PENDING: "⏳ Заявка на рассмотрении у водителя",
        }
    )

    past_time_text: str = "⛔ Это время уже прошло. Выберите время в будущем."
    past_date_text: str = "⛔ Нельзя создать поездку на прошедшую дату."

    user_sort_modes: tuple[tuple[str, str, str, bool], ...] = (
        ("reg_desc", "📅 Новизна ↓", "registration_date", True),
        ("reg_asc", "📅 Новизна ↑", "registration_date", False),
        ("bal_desc", "💰 Баланс ↓", "balance", True),
        ("bal_asc", "💰 Баланс ↑", "balance", False),
        ("rides_desc", "🚗 Поездки ↓", "total_rides", True),
        ("rides_asc", "🚗 Поездки ↑", "total_rides", False),
    )

    ride_edit_steps: dict[str, tuple[str, str]] = field(
        default_factory=lambda: {
            "edit_date": ("📅 Дата", "calendar"),
            "edit_time": ("🕒 Время", "time"),
            "edit_route": ("📍 Маршрут", "origin"),
            "edit_price": ("💰 Цена", "price"),
            "edit_seats": ("🪑 Места", "seats"),
            "edit_repeat": ("🔁 Повтор", "repeat_days"),
            "edit_remind": ("⏰ Напоминание", "remind"),
            "edit_vip": ("⭐ VIP-холд", "vip_hold"),
            "edit_auto": ("⚡ Авто-апрув", "auto_approve"),
            "edit_vis": ("👁️ Видимость", "visibility"),
            "edit_note": ("📝 Заметка", "note"),
        }
    )
