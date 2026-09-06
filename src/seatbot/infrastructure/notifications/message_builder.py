from datetime import datetime

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from seatbot.domain.schemas import Booking, BookingStatus, Ride, RideWithStats, User

BOOKING_STATUS_RU = {
    BookingStatus.PENDING: "ожидает",
    BookingStatus.APPROVED: "одобрена",
    BookingStatus.REJECTED: "отклонена",
    BookingStatus.CANCELLED: "отменена",
    BookingStatus.COMPLETED: "завершена",
    BookingStatus.NO_SHOW: "неявка",
}


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y %H:%M")


class MessageBuilder:
    @staticmethod
    def ride_card(ride: Ride | RideWithStats, free_seats: int | None = None) -> str:
        if isinstance(ride, RideWithStats):
            r = ride.ride
            free = ride.free_seats
            approved = ride.approved_seats
            pending = ride.pending_seats
        else:
            r = ride
            free = free_seats if free_seats is not None else r.seats_total
            approved = pending = 0
        price_str = "Бесплатно" if r.is_free else f"{r.price:.2f} BYN"
        status_emoji = {"open": "🟢", "closed": "🟡", "completed": "✅", "cancelled": "❌"}.get(
            r.status.value, "•"
        )
        lines = [
            f"{status_emoji} <b>Поездка</b>",
            f"🕒 Отправление: <b>{_fmt_dt(r.departure_at)}</b>",
            f"💰 Цена: <b>{price_str}</b>",
            f"🪑 Свободно мест: <b>{free}/{r.seats_total}</b>",
        ]
        if approved or pending:
            lines.append(f"   (подтверждено: {approved}, ожидает: {pending})")
        if r.auto_approve:
            lines.append("⚡ Авто-одобрение включено")
        if not r.is_visible:
            lines.append("👁️ Скрытая (видна только забронировавшим)")
        return "\n".join(lines)

    @staticmethod
    def payment_short(paid_amount: float, price: float, is_free: bool) -> str:
        if is_free:
            return "бесплатно"
        if paid_amount > 0:
            return f"деп {paid_amount:.2f} BYN"
        return f"нал {price:.2f} BYN"

    @staticmethod
    def payment_full(paid_amount: float, price: float, is_free: bool) -> str:
        if is_free:
            return "💰 Оплата: <b>Бесплатно</b>"
        if paid_amount > 0:
            return f"💰 Списано с депозита: <b>{paid_amount:.2f} BYN</b>"
        return f"💰 К оплате налом при встрече: <b>{price:.2f} BYN</b>"

    @staticmethod
    def booking_card(booking: Booking, ride: Ride, is_vip: bool = False) -> str:
        status_map = {
            BookingStatus.PENDING: "⏳ Ожидает подтверждения",
            BookingStatus.APPROVED: "✅ Одобрено",
            BookingStatus.REJECTED: "❌ Отклонено",
            BookingStatus.CANCELLED: "🚫 Отменено",
            BookingStatus.COMPLETED: "🏁 Завершено",
            BookingStatus.NO_SHOW: "🙅 Неявка",
        }
        payment = MessageBuilder.payment_full(
            booking.paid_amount, float(ride.price), ride.is_free or is_vip
        )
        return (
            f"<b>Бронь #{booking.booking_id}</b>\n"
            f"🕒 {_fmt_dt(ride.departure_at)}\n"
            f"{payment}\n"
            f"📋 Статус: {status_map.get(booking.status, BOOKING_STATUS_RU.get(booking.status, '—'))}"
        )

    @staticmethod
    def booking_approved_notification(ride: Ride, due_amount: float = 0.0) -> str:
        text = (
            f"✅ <b>Ваша бронь одобрена!</b>\n\n"
            f"Поездка в {_fmt_dt(ride.departure_at)}.\n"
            f"Жду вас, место закреплено."
        )
        if due_amount > 0:
            text += f"\n💰 К оплате на месте: <b>{due_amount:.2f} BYN</b> (наличными)"
        return text

    @staticmethod
    def booking_rejected_notification(ride: Ride) -> str:
        return (
            f"❌ <b>Ваша бронь отклонена.</b>\n\n"
            f"Поездка в {_fmt_dt(ride.departure_at)}.\n"
            f"Депозит возвращён на ваш баланс."
        )

    @staticmethod
    def booking_cancelled_by_admin_notification(ride: Ride) -> str:
        return (
            f"🚫 <b>Поездка отменена водителем.</b>\n\n"
            f"Поездка в {_fmt_dt(ride.departure_at)}.\n"
            f"Депозит возвращён на ваш баланс."
        )

    @staticmethod
    def ride_completed_notification(ride: Ride) -> str:
        return (
            f"🏁 <b>Поездка завершена.</b>\n\n"
            f"🕒 Отправление: {_fmt_dt(ride.departure_at)}\n"
            f"Спасибо за поездку!"
        )

    @staticmethod
    def no_show_notification(ride: Ride) -> str:
        return (
            f"🙅 <b>Отмечено, что вы не явились.</b>\n\n"
            f"Поездка в {_fmt_dt(ride.departure_at)}.\n"
            f"Возврат депозита не производится."
        )

    @staticmethod
    def new_booking_admin_log(booking: Booking, user: User, ride: Ride) -> str:
        vip_marker = " ⭐VIP" if user.is_vip else ""
        is_free = ride.is_free or user.is_vip
        if is_free:
            payment = "бесплатно" if ride.is_free else "бесплатно (VIP)"
        elif booking.paid_amount > 0:
            payment = f"списано с депозита {booking.paid_amount:.2f} BYN"
        else:
            payment = f"нал при встрече {float(ride.price):.2f} BYN"
        return (
            f"🆕 <b>Новая бронь</b>\n"
            f"Поездка {_fmt_dt(ride.departure_at)}\n"
            f"Пользователь: @{user.username or '—'} ({user.user_id}){vip_marker}\n"
            f"Бронь #{booking.booking_id}, оплата: {payment}"
        )

    @staticmethod
    def booking_approve_keyboard(booking_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Одобрить", callback_data=f"adm_approve:{booking_id}"
                    ),
                    InlineKeyboardButton(
                        text="❌ Отклонить", callback_data=f"adm_reject:{booking_id}"
                    ),
                ]
            ]
        )

    @staticmethod
    def new_user_admin_log(user: User) -> str:
        return (
            f"👋 <b>Новый пользователь</b>\n"
            f"@{user.username or '—'} ({user.user_id})"
        )

    @staticmethod
    def deposit_topup_notification(amount: float, new_balance: float) -> str:
        return (
            f"💰 <b>Депозит пополнен</b>\n\n"
            f"Зачислено: <b>+{amount:.2f} BYN</b>\n"
            f"Текущий баланс: <b>{new_balance:.2f} BYN</b>"
        )

    @staticmethod
    def deposit_decrease_notification(amount: float, new_balance: float) -> str:
        return (
            f"💸 <b>Депозит списан</b>\n\n"
            f"Списано: <b>-{amount:.2f} BYN</b>\n"
            f"Текущий баланс: <b>{new_balance:.2f} BYN</b>"
        )

    @staticmethod
    def ban_notification() -> str:
        return "🚫 Вы добавлены в чёрный список. Бронирование поездок недоступно."

    @staticmethod
    def unban_notification() -> str:
        return "✅ Вы удалены из чёрного списка. Бронирование снова доступно."

    @staticmethod
    def vip_granted_notification() -> str:
        return (
            "⭐ Вам выдан VIP-статус!\n\n"
            "Все поездки для вас бесплатны, бронирования одобряются автоматически."
        )

    @staticmethod
    def vip_revoked_notification() -> str:
        return "⭐ VIP-статус снят."

    @staticmethod
    def added_by_admin_notification(ride: Ride, due_amount: float = 0.0) -> str:
        text = (
            f"✅ <b>Вас добавили в поездку!</b>\n\n"
            f"Поездка в {_fmt_dt(ride.departure_at)}.\n"
            f"Место закреплено за вами. Жду вас!"
        )
        if due_amount > 0:
            text += f"\n💰 К оплате на месте: <b>{due_amount:.2f} BYN</b> (наличными)"
        return text

    @staticmethod
    def ride_reminder_notification(ride: Ride) -> str:
        return (
            f"⏰ <b>Напоминание о поездке!</b>\n\n"
            f"Поездка отправляется через "
            f"{ride.remind_minutes} мин.\n"
            f"🕒 Время: {_fmt_dt(ride.departure_at)}\n"
            f"Не опаздывайте!"
        )
