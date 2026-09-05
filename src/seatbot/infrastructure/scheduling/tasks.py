from datetime import UTC, datetime, timedelta

from dishka import AsyncContainer

from seatbot.application.services.bot import BotService
from seatbot.domain.schemas import BookingStatus, RideStatus
from seatbot.infrastructure.database.dao import BookingsDAO, RidesDAO
from seatbot.infrastructure.notifications import MessageBuilder


async def auto_close_past_rides(container: AsyncContainer) -> None:
    """Закрывает поездки, время отправления которых прошло более 30 минут назад."""
    async with container() as scope:
        rides_dao: RidesDAO = await scope.get(RidesDAO)

        now = datetime.now(UTC)
        active_rides = await rides_dao.list_active()
        for ride in active_rides:
            if ride.departure_at < now - timedelta(minutes=30):
                await rides_dao.set_status(ride.ride_id, RideStatus.CLOSED)


async def send_ride_reminders(container: AsyncContainer) -> None:
    """Отправляет напоминания за remind_minutes минут до отправления.

    Напоминания получают: approved, VIP, добавленные админом (все approved).
    Каждой поездке — только одно напоминание (проверяем remind_sent).
    """
    async with container() as scope:
        rides_dao: RidesDAO = await scope.get(RidesDAO)
        bookings_dao: BookingsDAO = await scope.get(BookingsDAO)
        bot_service: BotService = await scope.get(BotService)

        now = datetime.now(UTC)
        active_rides = await rides_dao.list_active()
        for ride in active_rides:
            remind_at = ride.departure_at - timedelta(minutes=ride.remind_minutes)
            if now < remind_at:
                continue
            if await rides_dao.is_remind_sent(ride.ride_id):
                continue
            approved = await bookings_dao.list_for_ride_with_status(
                ride.ride_id, {BookingStatus.APPROVED}
            )
            for booking in approved:
                await bot_service.notify_user(
                    booking.user_id, MessageBuilder.ride_reminder_notification(ride)
                )
            await rides_dao.mark_remind_sent(ride.ride_id)
