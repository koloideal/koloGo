from datetime import datetime
from html import escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from seatbot.domain.schemas import (Booking, BookingStatus, Ride, RideStatus,
                                    RideWithStats, User)
from seatbot.infrastructure.config.app import AppConfig
from seatbot.infrastructure.time import LocalClock


def fmt_amount(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.2f}"


def fmt_duration(seconds: float) -> str:
    mins = int(seconds // 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours} ч {mins} мин"
    return f"{mins} мин"


def user_display(username: str | None, first_name: str | None, user_id: int) -> str:
    if username:
        return f"@{username}"
    if first_name:
        return escape(first_name)
    return f"id{user_id}"


def route_str(ride: Ride) -> str | None:
    if ride.origin and ride.destination:
        return f"{escape(ride.origin)} → {escape(ride.destination)}"
    if ride.origin:
        return escape(ride.origin)
    if ride.destination:
        return escape(ride.destination)
    return None


def route_line(ride: Ride) -> str:
    route = route_str(ride)
    return f"📍 Маршрут: {route}\n" if route else ""


class MessageBuilder:
    def __init__(self, clock: LocalClock, app_config: AppConfig) -> None:
        self._clock = clock
        self._booking_status_ru = app_config.booking_status_ru
        self._weekdays_ru = app_config.weekdays_ru

    def departure_lines(self, r: Ride) -> list[str]:
        if r.started_at:
            return [
                f"🕒 Отправление (план): <b>{self._clock.fmt(r.departure_at)}</b>",
                f"🛣 Выехали: <b>{self._clock.fmt(r.started_at)}</b>",
            ]
        return [f"🕒 Отправление: <b>{self._clock.fmt(r.departure_at)}</b>"]

    def ride_card(self, ride: Ride | RideWithStats, free_seats: int | None = None) -> str:
        if isinstance(ride, RideWithStats):
            r = ride.ride
            free = ride.free_seats
            approved = ride.approved_seats
            pending = ride.pending_seats
            finished = ride.finished_seats
        else:
            r = ride
            free = free_seats if free_seats is not None else r.seats_total
            approved = pending = finished = 0
        price_str = "Бесплатно" if r.is_free else f"{fmt_amount(r.price)} BYN"
        status_emoji = {
            "open": "🟢",
            "closed": "🟡",
            "in_progress": "🚙",
            "completed": "✅",
            "cancelled": "❌",
        }.get(r.status.value, "•")
        lines = [f"{status_emoji} <b>Поездка</b>"]
        lines.extend(self.departure_lines(r))
        route = route_str(r)
        if route:
            lines.append(f"📍 Маршрут: <b>{route}</b>")
        lines.append(f"💰 Цена: <b>{price_str}</b>")
        if r.status == RideStatus.COMPLETED:
            lines.append(f"🏁 Ехало: <b>{finished}/{r.seats_total}</b>")
            lines.extend(self.track_stats_lines(r))
        elif r.status == RideStatus.IN_PROGRESS:
            lines.append(f"🚙 <b>В пути</b> (дистанция: {r.track_distance_m / 1000:.1f} км)")
        elif r.status == RideStatus.CANCELLED:
            lines.append(f"🪑 Мест было: <b>{r.seats_total}</b>")
        else:
            lines.append(f"🪑 Свободно мест: <b>{free}/{r.seats_total}</b>")
        if approved or pending:
            lines.append(f"   (подтверждено: {approved}, ожидает: {pending})")
        if r.auto_approve:
            lines.append("⚡ Авто-одобрение включено")
        if not r.is_visible:
            lines.append("👁️ Скрытая (видна только забронировавшим)")
        if r.vip_hold_minutes > 0 and not r.is_vip_hold_active(self._clock.now()):
            lines.append(f"⭐ VIP-холд был {r.vip_hold_minutes} мин (истёк)")
        if r.note:
            lines.append(f"📝 {escape(r.note)}")
        return "\n".join(lines)

    def track_stats_lines(self, r: Ride) -> list[str]:
        if not r.started_at or not r.finished_at:
            return []
        duration = (r.finished_at - r.started_at).total_seconds()
        km = r.track_distance_m / 1000
        lines = [
            f"🏁 Прибыли: <b>{self._clock.fmt(r.finished_at)}</b>",
            f"⏱ В пути: <b>{fmt_duration(duration)}</b>",
            f"🛣 Дистанция: <b>{km:.1f} км</b>",
        ]
        if duration > 0 and km > 0:
            lines.append(f"⚡ Ср. скорость: <b>{km / (duration / 3600):.0f} км/ч</b>")
        if r.track_max_speed_mps > 0:
            lines.append(f"🚀 Макс. скорость: <b>{r.track_max_speed_mps * 3.6:.0f} км/ч</b>")
        return lines

    def payment_short(self, paid_amount: float, price: float, is_free: bool) -> str:
        if is_free:
            return "бесплатно"
        if paid_amount > 0:
            return f"деп {fmt_amount(paid_amount)} BYN"
        return f"по факту {fmt_amount(price)} BYN"

    def payment_full(self, paid_amount: float, price: float, is_free: bool) -> str:
        if is_free:
            return "💰 Оплата: <b>Бесплатно</b>"
        if paid_amount > 0:
            return f"💰 Списано с депозита: <b>{fmt_amount(paid_amount)} BYN</b>"
        return f"💰 Оплата по факту: <b>{fmt_amount(price)} BYN</b>"

    def booking_card(self, booking: Booking, ride: Ride, is_vip: bool = False) -> str:
        status_map = {
            BookingStatus.PENDING: "⏳ Ожидает подтверждения",
            BookingStatus.APPROVED: "✅ Одобрено",
            BookingStatus.REJECTED: "❌ Отклонено",
            BookingStatus.CANCELLED: "🚫 Отменено",
            BookingStatus.COMPLETED: "🏁 Завершено",
            BookingStatus.NO_SHOW: "🙅 Неявка",
        }
        payment = self.payment_full(booking.paid_amount, float(ride.price), ride.is_free or is_vip)
        lines = [f"<b>Бронь #{booking.booking_id}</b>"]
        lines.extend(self.departure_lines(ride))
        route = route_str(ride)
        if route:
            lines.append(f"📍 {route}")
        lines += [
            payment,
            f"📋 Статус: {status_map.get(booking.status, self._booking_status_ru.get(booking.status, '—'))}",
        ]
        if ride.status == RideStatus.COMPLETED:
            lines.extend(self.track_stats_lines(ride))
        if ride.note:
            lines.append(f"📝 {escape(ride.note)}")
        return "\n".join(lines)

    def booking_approved_notification(self, ride: Ride, due_amount: float = 0.0) -> str:
        text = (
            f"✅ <b>Ваша бронь одобрена!</b>\n\n"
            f"Поездка в {self._clock.fmt(ride.departure_at)}.\n"
            f"{route_line(ride)}"
            f"Жду вас, место закреплено."
        )
        if due_amount > 0:
            text += f"\n💰 Оплата по факту: <b>{fmt_amount(due_amount)} BYN</b>"
        return text

    def booking_rejected_notification(self, ride: Ride, paid_amount: float = 0.0) -> str:
        text = (
            f"❌ <b>Ваша бронь отклонена.</b>\n\n"
            f"Поездка в {self._clock.fmt(ride.departure_at)}.\n"
            f"{route_line(ride)}"
        )
        if paid_amount > 0:
            text += f"Депозит <b>{fmt_amount(paid_amount)} BYN</b> возвращён на ваш баланс."
        elif ride.is_free:
            text += "Поездка была бесплатной."
        else:
            text += "С вас ничего не списывалось — оплата была по факту."
        return text

    def booking_rejected_no_seats_notification(self, ride: Ride) -> str:
        return (
            f"❌ <b>Ваша заявка отклонена — все места заняты.</b>\n\n"
            f"Поездка в {self._clock.fmt(ride.departure_at)}.\n"
            f"{route_line(ride)}"
            "С вас ничего не списывалось. Если место освободится, можно подать заявку снова."
        )

    def booking_cancelled_by_admin_notification(self, ride: Ride, paid_amount: float = 0.0) -> str:
        text = (
            f"🚫 <b>Поездка отменена водителем.</b>\n\n"
            f"Поездка в {self._clock.fmt(ride.departure_at)}.\n"
            f"{route_line(ride)}"
        )
        if paid_amount > 0:
            text += f"Депозит <b>{fmt_amount(paid_amount)} BYN</b> возвращён на ваш баланс."
        elif ride.is_free:
            text += "Поездка была бесплатной."
        else:
            text += "С вас ничего не списывалось — оплата была по факту."
        return text

    def ride_completed_notification(
        self, ride: Ride, paid_amount: float = 0.0, price: float = 0.0, is_free: bool = False
    ) -> str:
        lines = ["🏁 <b>Приехали! Поездка завершена.</b>\n"]
        route = route_str(ride)
        if route:
            lines.append(f"📍 Маршрут: <b>{route}</b>")
        lines.extend(self.departure_lines(ride))
        lines.extend(self.track_stats_lines(ride))
        if is_free:
            lines.append("💰 Поездка бесплатная.")
        elif paid_amount > 0:
            lines.append(f"💰 Списано с депозита: <b>{fmt_amount(paid_amount)} BYN</b>")
        else:
            lines.append(f"💰 Оплата по факту: <b>{fmt_amount(price)} BYN</b>")
        lines.append("\nСпасибо за поездку!")
        return "\n".join(lines)

    def no_show_notification(self, ride: Ride) -> str:
        return (
            f"🙅 <b>Отмечено, что вы не явились.</b>\n\n"
            f"Поездка в {self._clock.fmt(ride.departure_at)}.\n"
            f"{route_line(ride)}"
            f"Возврат депозита не производится."
        )

    def booking_kicked_notification(self, ride: Ride, reason: str) -> str:
        text = (
            f"🚫 <b>Вас убрали из поездки.</b>\n\n"
            f"Поездка в {self._clock.fmt(ride.departure_at)}.\n"
            f"{route_line(ride)}"
        )
        if reason:
            text += f"Причина: <i>{escape(reason)}</i>\n"
        text += "Бронь отменена."
        return text

    def booking_cancelled_by_user_admin_log(self, booking: Booking, user: User, ride: Ride) -> str:
        vip_marker = " ⭐VIP" if user.is_vip else ""
        is_free = ride.is_free or user.is_vip
        if is_free:
            payment = "бесплатно"
        elif booking.paid_amount > 0:
            payment = f"возврат с депозита {fmt_amount(booking.paid_amount)} BYN"
        else:
            payment = "по факту (возврат не требуется)"
        return (
            f"🚫 <b>Пользователь отменил бронь</b>\n"
            f"Поездка {self._clock.fmt(ride.departure_at)}\n"
            f"{route_line(ride)}"
            f"Пользователь: {user_display(user.username, user.first_name, user.user_id)} "
            f"({user.user_id}){vip_marker}\n"
            f"Бронь #{booking.booking_id}, оплата: {payment}"
        )

    def user_brief(self, user: User, counts: dict[BookingStatus, int]) -> str:
        no_show = counts.get(BookingStatus.NO_SHOW, 0)
        history = (
            f"🧾 Поездок: <b>{counts.get(BookingStatus.COMPLETED, 0)}</b> · "
            f"неявок: <b>{no_show}</b>{' ⚠️' if no_show else ''} · "
            f"отмен: <b>{counts.get(BookingStatus.CANCELLED, 0)}</b> · "
            f"отклонено: <b>{counts.get(BookingStatus.REJECTED, 0)}</b>"
        )
        since = self._clock.fmt(user.registration_date, "%d.%m.%Y")
        return f"{history}\n💰 Баланс: <b>{fmt_amount(user.balance)} BYN</b> · с нами с {since}"

    @staticmethod
    def seats_line(ride: Ride, approved: int, pending: int) -> str:
        return f"🪑 Одобрено: <b>{approved}/{ride.seats_total}</b> · заявок: <b>{pending}</b>"

    def new_booking_admin_log(
        self,
        booking: Booking,
        user: User,
        ride: Ride,
        counts: dict[BookingStatus, int] | None = None,
        seats: tuple[int, int] | None = None,
    ) -> str:
        vip_marker = " ⭐VIP" if user.is_vip else ""
        is_free = ride.is_free or user.is_vip
        if is_free:
            payment = "бесплатно" if ride.is_free else "бесплатно (VIP)"
        elif booking.paid_amount > 0:
            payment = f"списано с депозита {fmt_amount(booking.paid_amount)} BYN"
        else:
            payment = f"по факту {fmt_amount(float(ride.price))} BYN"
        text = (
            f"🆕 <b>Новая бронь</b>\n"
            f"Поездка {self._clock.fmt(ride.departure_at)}\n"
            f"{route_line(ride)}"
            f"Пользователь: {user_display(user.username, user.first_name, user.user_id)} "
            f"({user.user_id}){vip_marker}\n"
            f"Бронь #{booking.booking_id}, оплата: {payment}"
        )
        if counts is not None:
            text += f"\n\n{self.user_brief(user, counts)}"
        if seats is not None:
            text += f"\n{self.seats_line(ride, *seats)}"
        return text

    def booking_approve_keyboard(self, booking_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Одобрить", callback_data=f"adm_approve:{booking_id}"),
                    InlineKeyboardButton(text="❌ Отклонить", callback_data=f"adm_reject:{booking_id}"),
                ]
            ]
        )

    def new_user_admin_log(self, user: User) -> str:
        return (
            f"👋 <b>Новый пользователь</b>\n"
            f"{user_display(user.username, user.first_name, user.user_id)} ({user.user_id})"
        )

    def deposit_topup_notification(self, amount: float, new_balance: float) -> str:
        return (
            f"💰 <b>Депозит пополнен</b>\n\n"
            f"Зачислено: <b>+{fmt_amount(amount)} BYN</b>\n"
            f"Текущий баланс: <b>{fmt_amount(new_balance)} BYN</b>"
        )

    def deposit_decrease_notification(self, amount: float, new_balance: float) -> str:
        return (
            f"💸 <b>Депозит списан</b>\n\n"
            f"Списано: <b>-{fmt_amount(amount)} BYN</b>\n"
            f"Текущий баланс: <b>{fmt_amount(new_balance)} BYN</b>"
        )

    def new_ride_notification(self, ride: Ride) -> str:
        price = "Бесплатно" if ride.is_free else f"{fmt_amount(ride.price)} BYN"
        note = f"\n📝 {escape(ride.note)}" if ride.note else ""
        if ride.vip_hold_minutes > 0:
            hold = (
                f"\n⭐ <b>VIP-холд {ride.vip_hold_minutes} мин</b> — "
                "сначала бронируют VIP, потом все остальные."
            )
        else:
            hold = ""
        return (
            "🚗 <b>Новая поездка!</b>\n\n"
            f"🕒 Отправление: <b>{self._clock.fmt(ride.departure_at)}</b>\n"
            f"{route_line(ride)}"
            f"💰 Цена: <b>{price}</b>{note}{hold}"
        )

    def new_rides_notification(self, rides: list[Ride]) -> str:
        first = rides[0]
        price = "Бесплатно" if first.is_free else f"{fmt_amount(first.price)} BYN"
        dates = "\n".join(f"• {self.short_date(r.departure_at)}" for r in rides)
        note = f"\n📝 {escape(first.note)}" if first.note else ""
        hold = (
            f"\n⭐ <b>VIP-холд {first.vip_hold_minutes} мин</b> — сначала бронируют VIP, потом все остальные."
            if first.vip_hold_minutes > 0
            else ""
        )
        return (
            f"🚗 <b>Новые поездки: {len(rides)}</b>\n\n"
            f"{route_line(first)}"
            f"💰 Цена: <b>{price}</b>{note}{hold}\n\n"
            f"🕒 Даты:\n{dates}\n\n"
            "Выберите дату ниже, чтобы забронировать место."
        )

    def added_by_admin_notification(self, ride: Ride, due_amount: float = 0.0) -> str:
        text = (
            f"✅ <b>Вас добавили в поездку!</b>\n\n"
            f"Поездка в {self._clock.fmt(ride.departure_at)}.\n"
            f"{route_line(ride)}"
            f"Место закреплено за вами. Жду вас!"
        )
        if due_amount > 0:
            text += f"\n💰 Оплата по факту: <b>{fmt_amount(due_amount)} BYN</b>"
        return text

    def _departs_in(self, ride: Ride) -> str:
        minutes = int((ride.departure_at - self._clock.now()).total_seconds() // 60)
        return f"через {minutes} мин." if minutes > 0 else "прямо сейчас."

    def ride_reminder_notification(self, ride: Ride) -> str:
        return (
            f"⏰ <b>Напоминание о поездке!</b>\n\n"
            f"Поездка отправляется {self._departs_in(ride)}\n"
            f"🕒 Время: {self._clock.fmt(ride.departure_at)}\n"
            f"{route_line(ride)}"
            f"Не опаздывайте!"
        )

    def driver_departed_notification(self, ride: Ride) -> str:
        return (
            "🚙 <b>Водитель выехал!</b>\n\n"
            f"🕒 Поездка: {self._clock.fmt(ride.departure_at)}\n"
            f"{route_line(ride)}"
            "Подходите к месту отправления."
        )

    def ride_time_changed_notification(self, ride: Ride, old_departure: datetime) -> str:
        return (
            f"🕒 <b>Время поездки изменено!</b>\n\n"
            f"{route_line(ride)}"
            f"Было: <s>{self._clock.fmt(old_departure)}</s>\n"
            f"Стало: <b>{self._clock.fmt(ride.departure_at)}</b>\n\n"
            "Пожалуйста, учитывайте новое время."
        )

    def ride_time_changed_admin_log(self, ride: Ride, old_departure: datetime, approved_count: int) -> str:
        return (
            f"🕒 <b>Изменено время поездки</b>\n\n"
            f"{route_line(ride)}"
            f"Было: <s>{self._clock.fmt(old_departure)}</s>\n"
            f"Стало: <b>{self._clock.fmt(ride.departure_at)}</b>\n"
            f"Уведомлено пассажиров: <b>{approved_count}</b>"
        )

    def vip_info_text(self, price: float, is_vip: bool, balance: float) -> str:
        if is_vip:
            return (
                "⭐ <b>Вы уже VIP!</b>\n\n"
                "Ваши привилегии:\n"
                "• Все поездки бесплатны\n"
                "• Авто-одобрение без ожидания\n"
                "• Доступ к бронированию во время VIP-холда\n\n"
                "Спасибо за поддержку проекта! 🙏"
            )
        lines = [
            "⭐ <b>VIP-статус</b>\n",
            "<b>Привилегии VIP:</b>",
            "• 🚗 Все поездки бесплатны",
            "• ⚡ Авто-одобрение без ожидания водителя",
            ("• 🏃 Доступ к бронированию во время VIP-холда (первые минуты после публикации поездки)"),
            "",
            f"💰 Стоимость: <b>{fmt_amount(price)} BYN</b> (единоразово)",
            f"💳 Ваш баланс: <b>{fmt_amount(balance)} BYN</b>",
        ]
        if balance >= price:
            lines.append("\n✅ У вас достаточно средств для покупки.")
        else:
            shortage = price - balance
            lines.append(
                f"\n❌ Не хватает <b>{fmt_amount(shortage)} BYN</b>. Попросите админа пополнить депозит."
            )
        return "\n".join(lines)

    def vip_purchase_notification(self, price: float, new_balance: float) -> str:
        return (
            "⭐ <b>VIP-статус активирован!</b>\n\n"
            f"Списано: <b>-{fmt_amount(price)} BYN</b>\n"
            f"Текущий баланс: <b>{fmt_amount(new_balance)} BYN</b>\n\n"
            "Теперь все поездки для вас бесплатны, а брони "
            "одобряются автоматически. Спасибо за поддержку! 🙏"
        )

    def vip_purchased_admin_log(self, user: User, price: float) -> str:
        name = escape(user.first_name or user.username or str(user.user_id))
        return (
            f"⭐ <b>VIP куплен</b>\n\n"
            f"Пользователь: {name} (<code>{user.user_id}</code>)\n"
            f"Списано: <b>{fmt_amount(price)} BYN</b>"
        )

    def book_rides_keyboard(self, rides: list[Ride]) -> InlineKeyboardMarkup:
        if len(rides) == 1:
            rows = [
                [InlineKeyboardButton(text="🚗 К поездке", callback_data=f"open_ride:{rides[0].ride_id}")]
            ]
        else:
            rows = [
                [
                    InlineKeyboardButton(
                        text=f"🚗 {self.short_date(r.departure_at)}", callback_data=f"open_ride:{r.ride_id}"
                    )
                ]
                for r in rides
            ]
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def origin_keyboard(self, ride: Ride) -> InlineKeyboardMarkup | None:
        if ride.origin_lat is None or ride.origin_lon is None:
            return None
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📍 Место отправления", callback_data=f"ride_origin:{ride.ride_id}"
                    )
                ]
            ]
        )

    def short_date(self, dt: datetime) -> str:
        local = self._clock.to_local(dt)
        return f"{local:%d.%m} ({self._weekdays_ru[local.weekday()]}) {local:%H:%M}"

    def ride_map_keyboard(self, map_url: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🗺 Маршрут на карте", url=map_url)]]
        )

    def ride_completed_admin_log(self, ride: Ride, passengers_count: int) -> str:
        lines = [
            f"🏁 <b>Поездка #{ride.ride_id} завершена</b>\n",
            f"📍 Маршрут: {route_str(ride) or '—'}",
            f"🧍 Ехало: <b>{passengers_count}</b>",
        ]
        lines.extend(self.departure_lines(ride))
        lines.extend(self.track_stats_lines(ride))
        return "\n".join(lines)

    def tracking_started_admin_log(self, ride: Ride) -> str:
        lines = [
            "🚙 <b>Трекинг поездки запущен</b>\n",
        ]
        lines.extend(self.departure_lines(ride))
        lines.append(route_line(ride).rstrip("\n"))
        lines.append(
            "Бот следит за live-гео и завершит поездку автоматически по прибытии в точку назначения."
        )
        return "\n".join(lines)

    def tracking_stopped_admin_log(self, ride_id: int, distance_m: float | None = None) -> str:
        where = (
            f"До точки прибытия оставалось ~{distance_m / 1000:.1f} км.\n" if distance_m is not None else ""
        )
        return (
            f"⚠️ <b>Live-гео поездки #{ride_id} остановлено.</b>\n\n"
            f"{where}"
            "Трекинг прекращён. Завершите поездку вручную в меню поездок."
        )

    def ride_not_started_admin_log(self, ride: Ride, approved_count: int, auto_complete_after_h: int) -> str:
        return (
            f"⚠️ <b>Поездка #{ride.ride_id} не стартовала</b>\n\n"
            f"🕒 Время: {self._clock.fmt(ride.departure_at)}\n"
            f"{route_line(ride)}"
            f"🪑 Подтверждённых пассажиров: <b>{approved_count}</b>\n\n"
            "Запись закрыта. Завершите поездку, чтобы списать оплату, или отмените её.\n"
            f"<i>Через {auto_complete_after_h} ч после выезда поездка завершится автоматически.</i>"
        )

    def ride_not_started_keyboard(self, ride_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🏁 Завершить", callback_data=f"adm_complete:{ride_id}"),
                    InlineKeyboardButton(text="🚗 К поездке", callback_data=f"adm_ride:{ride_id}"),
                ]
            ]
        )

    def ride_reminder_admin_notification(self, ride: Ride, approved_count: int) -> str:
        return (
            f"⏰ <b>Напоминание: поездка скоро отправляется</b>\n\n"
            f"🕒 Время: {self._clock.fmt(ride.departure_at)}\n"
            f"{route_line(ride)}"
            f"⏳ Отправление: <b>{self._departs_in(ride)}</b>\n"
            f"🪑 Подтверждённых пассажиров: <b>{approved_count}</b>"
        )

    def balance_info_text(self, balance: float, is_vip: bool) -> str:
        lines = [
            "💰 <b>Баланс</b>\n",
            f"Текущий баланс: <b>{fmt_amount(balance)} BYN</b>\n",
            "<b>Зачем нужен баланс:</b>",
            "🚗 Оплата поездок — после поездки сумма списывается с депозита (если средств не хватает — оплата по факту)",
            "⭐ Покупка VIP-статуса — кнопка в главном меню",
        ]
        if is_vip:
            lines.append("\n⭐ У вас уже есть VIP — поездки бесплатны!")
        return "\n".join(lines)

    def payment_success_notification(self, amount: float, new_balance: float) -> str:
        return (
            "✅ <b>Баланс пополнен!</b>\n\n"
            f"Зачислено: <b>+{fmt_amount(amount)} BYN</b>\n"
            f"Текущий баланс: <b>{fmt_amount(new_balance)} BYN</b>"
        )

    def payment_expired_notification(self) -> str:
        return "⏰ <b>Время оплаты истекло</b>\n\nИнвойс отменён. Попробуйте пополнить баланс снова."

    def payment_admin_log(self, user: User, amount: float, method: str = "CryptoBot (USDT)") -> str:
        name = escape(user.first_name or user.username or str(user.user_id))
        return (
            f"💰 <b>Пополнение баланса</b>\n\n"
            f"Пользователь: {name} (<code>{user.user_id}</code>)\n"
            f"Сумма: <b>{fmt_amount(amount)} BYN</b>\n"
            f"Способ: {method}"
        )
