from datetime import datetime
from html import escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from seatbot.domain.schemas import Booking, BookingStatus, Ride, RideWithStats, User
from seatbot.infrastructure.time import LocalClock

BOOKING_STATUS_RU = {
    BookingStatus.PENDING: "ожидает",
    BookingStatus.APPROVED: "одобрена",
    BookingStatus.REJECTED: "отклонена",
    BookingStatus.CANCELLED: "отменена",
    BookingStatus.COMPLETED: "завершена",
    BookingStatus.NO_SHOW: "неявка",
}


def fmt_amount(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.2f}"


def user_display(username: str | None, first_name: str | None, user_id: int) -> str:
    if username:
        return f"@{username}"
    if first_name:
        return escape(first_name)
    return f"id{user_id}"


class MessageBuilder:
    def __init__(self, clock: LocalClock) -> None:
        self._clock = clock

    def ride_card(self, ride: Ride | RideWithStats, free_seats: int | None = None) -> str:
        if isinstance(ride, RideWithStats):
            r = ride.ride
            free = ride.free_seats
            approved = ride.approved_seats
            pending = ride.pending_seats
        else:
            r = ride
            free = free_seats if free_seats is not None else r.seats_total
            approved = pending = 0
        price_str = "Бесплатно" if r.is_free else f"{fmt_amount(r.price)} BYN"
        status_emoji = {"open": "🟢", "closed": "🟡", "completed": "✅", "cancelled": "❌"}.get(
            r.status.value, "•"
        )
        lines = [
            f"{status_emoji} <b>Поездка</b>",
            f"🕒 Отправление: <b>{self._clock.fmt(r.departure_at)}</b>",
            f"💰 Цена: <b>{price_str}</b>",
            f"🪑 Свободно мест: <b>{free}/{r.seats_total}</b>",
        ]
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
        lines = [
            f"<b>Бронь #{booking.booking_id}</b>",
            f"🕒 {self._clock.fmt(ride.departure_at)}",
            payment,
            f"📋 Статус: {status_map.get(booking.status, BOOKING_STATUS_RU.get(booking.status, '—'))}",
        ]
        if ride.note:
            lines.append(f"📝 {escape(ride.note)}")
        return "\n".join(lines)

    def booking_approved_notification(self, ride: Ride, due_amount: float = 0.0) -> str:
        text = (
            f"✅ <b>Ваша бронь одобрена!</b>\n\n"
            f"Поездка в {self._clock.fmt(ride.departure_at)}.\n"
            f"Жду вас, место закреплено."
        )
        if due_amount > 0:
            text += f"\n💰 Оплата по факту: <b>{fmt_amount(due_amount)} BYN</b>"
        return text

    def booking_rejected_notification(self, ride: Ride, paid_amount: float = 0.0) -> str:
        text = (
            f"❌ <b>Ваша бронь отклонена.</b>\n\n"
            f"Поездка в {self._clock.fmt(ride.departure_at)}.\n"
        )
        if paid_amount > 0:
            text += f"Депозит <b>{fmt_amount(paid_amount)} BYN</b> возвращён на ваш баланс."
        elif ride.is_free:
            text += "Поездка была бесплатной."
        else:
            text += "С вас ничего не списывалось — оплата была по факту."
        return text

    def booking_cancelled_by_admin_notification(self, ride: Ride, paid_amount: float = 0.0) -> str:
        text = (
            f"🚫 <b>Поездка отменена водителем.</b>\n\n"
            f"Поездка в {self._clock.fmt(ride.departure_at)}.\n"
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
        text = (
            f"🏁 <b>Поездка завершена.</b>\n\n"
            f"🕒 Отправление: {self._clock.fmt(ride.departure_at)}\n"
        )
        if is_free:
            text += "💰 Поездка бесплатная."
        elif paid_amount > 0:
            text += f"💰 Списано с депозита: <b>{fmt_amount(paid_amount)} BYN</b>."
        else:
            text += f"💰 Оплата по факту: <b>{fmt_amount(price)} BYN</b>."
        text += "\nСпасибо за поездку!"
        return text

    def no_show_notification(self, ride: Ride) -> str:
        return (
            f"🙅 <b>Отмечено, что вы не явились.</b>\n\n"
            f"Поездка в {self._clock.fmt(ride.departure_at)}.\n"
            f"Возврат депозита не производится."
        )

    def booking_kicked_notification(self, ride: Ride, reason: str) -> str:
        text = (
            f"🚫 <b>Вас убрали из поездки.</b>\n\n"
            f"Поездка в {self._clock.fmt(ride.departure_at)}.\n"
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
            f"Пользователь: {user_display(user.username, user.first_name, user.user_id)} "
            f"({user.user_id}){vip_marker}\n"
            f"Бронь #{booking.booking_id}, оплата: {payment}"
        )

    def new_booking_admin_log(self, booking: Booking, user: User, ride: Ride) -> str:
        vip_marker = " ⭐VIP" if user.is_vip else ""
        is_free = ride.is_free or user.is_vip
        if is_free:
            payment = "бесплатно" if ride.is_free else "бесплатно (VIP)"
        elif booking.paid_amount > 0:
            payment = f"списано с депозита {fmt_amount(booking.paid_amount)} BYN"
        else:
            payment = f"по факту {fmt_amount(float(ride.price))} BYN"
        return (
            f"🆕 <b>Новая бронь</b>\n"
            f"Поездка {self._clock.fmt(ride.departure_at)}\n"
            f"Пользователь: {user_display(user.username, user.first_name, user.user_id)} "
            f"({user.user_id}){vip_marker}\n"
            f"Бронь #{booking.booking_id}, оплата: {payment}"
        )

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
            f"💰 Цена: <b>{price}</b>{note}{hold}\n\n"
            "Откройте раздел «Поездки», чтобы забронировать место."
        )

    def added_by_admin_notification(self, ride: Ride, due_amount: float = 0.0) -> str:
        text = (
            f"✅ <b>Вас добавили в поездку!</b>\n\n"
            f"Поездка в {self._clock.fmt(ride.departure_at)}.\n"
            f"Место закреплено за вами. Жду вас!"
        )
        if due_amount > 0:
            text += f"\n💰 Оплата по факту: <b>{fmt_amount(due_amount)} BYN</b>"
        return text

    def ride_reminder_notification(self, ride: Ride) -> str:
        return (
            f"⏰ <b>Напоминание о поездке!</b>\n\n"
            f"Поездка отправляется через "
            f"{ride.remind_minutes} мин.\n"
            f"🕒 Время: {self._clock.fmt(ride.departure_at)}\n"
            f"Не опаздывайте!"
        )

    def ride_time_changed_notification(self, ride: Ride, old_departure: datetime) -> str:
        return (
            f"🕒 <b>Время поездки изменено!</b>\n\n"
            f"Было: <s>{self._clock.fmt(old_departure)}</s>\n"
            f"Стало: <b>{self._clock.fmt(ride.departure_at)}</b>\n\n"
            "Пожалуйста, учитывайте новое время."
        )

    def ride_time_changed_admin_log(self, ride: Ride, old_departure: datetime, approved_count: int) -> str:
        return (
            f"🕒 <b>Изменено время поездки</b>\n\n"
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
            (
                "• 🏃 Доступ к бронированию во время VIP-холда "
                "(первые минуты после публикации поездки)"
            ),
            "",
            f"💰 Стоимость: <b>{fmt_amount(price)} BYN</b> (единоразово)",
            f"💳 Ваш баланс: <b>{fmt_amount(balance)} BYN</b>",
        ]
        if balance >= price:
            lines.append("\n✅ У вас достаточно средств для покупки.")
        else:
            shortage = price - balance
            lines.append(
                f"\n❌ Не хватает <b>{fmt_amount(shortage)} BYN</b>. "
                "Попросите админа пополнить депозит."
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

    def ride_reminder_admin_notification(self, ride: Ride, approved_count: int) -> str:
        return (
            f"⏰ <b>Напоминание: поездка скоро отправляется</b>\n\n"
            f"🕒 Время: {self._clock.fmt(ride.departure_at)}\n"
            f"⏳ Через: <b>{ride.remind_minutes} мин.</b>\n"
            f"🪑 Подтверждённых пассажиров: <b>{approved_count}</b>"
        )

    def balance_info_text(self, balance: float, is_vip: bool) -> str:
        lines = [
            "💰 <b>Баланс</b>\n",
            f"Текущий баланс: <b>{fmt_amount(balance)} BYN</b>\n",
            "<b>Зачем нужен баланс:</b>",
            "🚗 Оплата поездок — при бронировании сумма списывается с депозита",
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
        return (
            "⏰ <b>Время оплаты истекло</b>\n\n"
            "Инвойс отменён. Попробуйте пополнить баланс снова."
        )

    def payment_admin_log(self, user: User, amount: float) -> str:
        name = escape(user.first_name or user.username or str(user.user_id))
        return (
            f"💰 <b>Пополнение баланса</b>\n\n"
            f"Пользователь: {name} (<code>{user.user_id}</code>)\n"
            f"Сумма: <b>{fmt_amount(amount)} BYN</b>\n"
            f"Способ: CryptoBot (USDT)"
        )
