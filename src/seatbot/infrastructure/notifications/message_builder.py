from datetime import datetime

from seatbot.domain.schemas import Booking, BookingStatus, Ride, RideWithStats, User


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y %H:%M")


class MessageBuilder:
    """Централизованный построитель текстов уведомлений (без i18n — только русский)."""

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
            f"{status_emoji} <b>Поездка #{r.ride_id}</b>",
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
    def booking_card(booking: Booking, ride: Ride) -> str:
        status_map = {
            BookingStatus.PENDING: "⏳ Ожидает подтверждения",
            BookingStatus.APPROVED: "✅ Одобрено",
            BookingStatus.REJECTED: "❌ Отклонено",
            BookingStatus.CANCELLED: "🚫 Отменено",
            BookingStatus.COMPLETED: "🏁 Завершено",
            BookingStatus.NO_SHOW: "🙅 Не явился",
        }
        price_str = "Бесплатно" if booking.paid_amount <= 0 else f"{booking.paid_amount:.2f} BYN"
        return (
            f"<b>Бронь #{booking.booking_id}</b> на поездку #{ride.ride_id}\n"
            f"🕒 {_fmt_dt(ride.departure_at)}\n"
            f"💰 Списано: {price_str}\n"
            f"📋 Статус: {status_map.get(booking.status, booking.status.value)}"
        )

    @staticmethod
    def booking_approved_notification(ride: Ride) -> str:
        return (
            f"✅ <b>Ваша бронь одобрена!</b>\n\n"
            f"Поездка #{ride.ride_id} в {_fmt_dt(ride.departure_at)}.\n"
            f"Жду вас, место закреплено."
        )

    @staticmethod
    def booking_rejected_notification(ride: Ride) -> str:
        return (
            f"❌ <b>Ваша бронь отклонена.</b>\n\n"
            f"Поездка #{ride.ride_id} в {_fmt_dt(ride.departure_at)}.\n"
            f"Депозит возвращён на ваш баланс."
        )

    @staticmethod
    def booking_cancelled_by_admin_notification(ride: Ride) -> str:
        return (
            f"🚫 <b>Поездка отменена водителем.</b>\n\n"
            f"Поездка #{ride.ride_id} в {_fmt_dt(ride.departure_at)}.\n"
            f"Депозит возвращён на ваш баланс."
        )

    @staticmethod
    def ride_completed_notification(ride: Ride) -> str:
        return (
            f"🏁 <b>Поездка #{ride.ride_id} завершена.</b>\n\n"
            f"🕒 Отправление: {_fmt_dt(ride.departure_at)}\n"
            f"Спасибо за поездку!"
        )

    @staticmethod
    def no_show_notification(ride: Ride) -> str:
        return (
            f"🙅 <b>Отмечено, что вы не явились.</b>\n\n"
            f"Поездка #{ride.ride_id} в {_fmt_dt(ride.departure_at)}.\n"
            f"Возврат депозита не производится."
        )

    @staticmethod
    def new_booking_admin_log(booking: Booking, user: User, ride: Ride) -> str:
        vip_marker = " ⭐VIP" if user.is_vip else ""
        return (
            f"🆕 <b>Новая бронь</b>\n"
            f"Поездка #{ride.ride_id} ({_fmt_dt(ride.departure_at)})\n"
            f"Пользователь: @{user.username or '—'} ({user.user_id}){vip_marker}\n"
            f"Бронь #{booking.booking_id}, списано {booking.paid_amount:.2f} BYN"
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
    def added_by_admin_notification(ride: Ride) -> str:
        return (
            f"✅ <b>Вас добавили в поездку!</b>\n\n"
            f"Поездка #{ride.ride_id} в {_fmt_dt(ride.departure_at)}.\n"
            f"Место закреплено за вами. Жду вас!"
        )

    @staticmethod
    def ride_reminder_notification(ride: Ride) -> str:
        return (
            f"⏰ <b>Напоминание о поездке!</b>\n\n"
            f"Поездка #{ride.ride_id} отправляется через "
            f"{ride.remind_minutes} мин.\n"
            f"🕒 Время: {_fmt_dt(ride.departure_at)}\n"
            f"Не опаздывайте!"
        )
