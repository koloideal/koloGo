import logging
from datetime import UTC, datetime, timedelta

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dishka import AsyncContainer

from seatbot.application.services.bot import BotService
from seatbot.domain.schemas import BookingStatus, RideStatus, TransactionStatus
from seatbot.infrastructure.database.dao import (BookingsDAO, RidesDAO, TransactionsDAO,
                                                 UsersDAO)
from seatbot.infrastructure.notifications import MessageBuilder
from seatbot.infrastructure.payments import CryptoBotPaymentService
from seatbot.infrastructure.time import LocalClock

logger = logging.getLogger(__name__)


async def auto_close_past_rides(container: AsyncContainer) -> None:
    async with container() as scope:
        rides_dao: RidesDAO = await scope.get(RidesDAO)
        clock: LocalClock = await scope.get(LocalClock)

        now = clock.now()
        active_rides = await rides_dao.list_active()
        for ride in active_rides:
            if ride.departure_at < now - timedelta(minutes=30):
                await rides_dao.set_status(ride.ride_id, RideStatus.CLOSED)


async def send_ride_reminders(container: AsyncContainer) -> None:
    async with container() as scope:
        rides_dao: RidesDAO = await scope.get(RidesDAO)
        bookings_dao: BookingsDAO = await scope.get(BookingsDAO)
        bot_service: BotService = await scope.get(BotService)
        messages: MessageBuilder = await scope.get(MessageBuilder)
        clock: LocalClock = await scope.get(LocalClock)

        now = clock.now()
        active_rides = await rides_dao.list_active()
        for ride in active_rides:
            if ride.remind_minutes <= 0:
                continue
            if await rides_dao.is_remind_sent(ride.ride_id):
                continue
            remind_at = ride.departure_at - timedelta(minutes=ride.remind_minutes)
            if now < remind_at:
                continue
            if now > ride.departure_at + timedelta(minutes=30):
                await rides_dao.mark_remind_sent(ride.ride_id)
                continue
            approved = await bookings_dao.list_for_ride_with_status(ride.ride_id, {BookingStatus.APPROVED})
            for booking in approved:
                await bot_service.notify_user(
                    booking.user_id, messages.ride_reminder_notification(ride)
                )
            await bot_service.send_log_to_admin(
                messages.ride_reminder_admin_notification(ride, len(approved))
            )
            await rides_dao.mark_remind_sent(ride.ride_id)


async def check_cryptobot_payment_status(
    payment_id: str,
    user_id: int,
    amount: float,
    created_at: datetime,
    container: AsyncContainer,
) -> None:
    scheduler: AsyncIOScheduler = await container.get(AsyncIOScheduler)
    cryptobot_service: CryptoBotPaymentService = await container.get(CryptoBotPaymentService)
    bot_service: BotService = await container.get(BotService)
    messages: MessageBuilder = await container.get(MessageBuilder)
    paid = False
    async with container() as scope:
        transactions_dao: TransactionsDAO = await scope.get(TransactionsDAO)
        users_dao: UsersDAO = await scope.get(UsersDAO)
        transaction = await transactions_dao.get_by_payment_id_for_update(payment_id)
        if not transaction or transaction.status != TransactionStatus.PENDING:
            return
        if (datetime.now(UTC) - created_at) > timedelta(minutes=15):
            await transactions_dao.update_status(payment_id, TransactionStatus.FAILED)
            user = await users_dao.get_by_id(user_id)
            if user:
                await bot_service.notify_user(user_id, messages.payment_expired_notification())
            return
        status = await cryptobot_service.check_payment(payment_id)
        if status == "paid":
            await transactions_dao.update_status(payment_id, TransactionStatus.COMPLETED)
            await users_dao.increase_balance(user_id, amount)
            user = await users_dao.get_by_id(user_id)
            if user:
                await bot_service.notify_user(
                    user_id, messages.payment_success_notification(amount, user.balance)
                )
                await bot_service.send_log_to_admin(messages.payment_admin_log(user, amount))
                paid = True
    try:
        scheduler.remove_job(f"check_payment_{payment_id}")
    except JobLookupError:
        logger.debug("Job check_payment_%s already removed", payment_id)
    if not paid:
        try:
            scheduler.remove_job(f"check_payment_{payment_id}")
        except JobLookupError:
            logger.debug("Job check_payment_%s already removed", payment_id)
