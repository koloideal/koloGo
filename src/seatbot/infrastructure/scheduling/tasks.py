import logging
from datetime import UTC, datetime, timedelta

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dishka import AsyncContainer

from seatbot.application.services.bot import BotService
from seatbot.application.services.tracking import TrackingService
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


async def finish_stale_arrivals(container: AsyncContainer) -> None:
    async with container() as scope:
        tracking_service: TrackingService = await scope.get(TrackingService)
        finished = await tracking_service.finish_stale_arrivals()
        if finished:
            logger.info("Auto-finished %s ride(s) stuck at destination", finished)


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
                    booking.user_id,
                    messages.ride_reminder_notification(ride),
                    reply_markup=messages.origin_keyboard(ride),
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
    logger.info(
        "check_cryptobot_payment_status: payment_id=%s user_id=%s amount=%s", payment_id, user_id, amount
    )
    scheduler: AsyncIOScheduler = await container.get(AsyncIOScheduler)
    cryptobot_service: CryptoBotPaymentService = await container.get(CryptoBotPaymentService)
    should_remove_job = False
    try:
        async with container() as scope:
            transactions_dao: TransactionsDAO = await scope.get(TransactionsDAO)
            users_dao: UsersDAO = await scope.get(UsersDAO)
            bot_service: BotService = await scope.get(BotService)
            messages: MessageBuilder = await scope.get(MessageBuilder)
            transaction = await transactions_dao.get_by_payment_id_for_update(payment_id)
            if not transaction:
                logger.warning("Transaction not found for payment_id=%s", payment_id)
                should_remove_job = True
                return
            logger.info(
                "Transaction %s: status=%s, amount=%s",
                payment_id,
                transaction.status,
                transaction.amount,
            )
            if transaction.status != TransactionStatus.PENDING:
                logger.info(
                    "Transaction %s not pending (status=%s), skipping", payment_id, transaction.status
                )
                should_remove_job = True
                return
            if (datetime.now(UTC) - created_at) > timedelta(minutes=15):
                logger.info("Transaction %s expired (15min timeout)", payment_id)
                await transactions_dao.update_status(payment_id, TransactionStatus.FAILED)
                user = await users_dao.get_by_id(user_id)
                if user:
                    await bot_service.notify_user(user_id, messages.payment_expired_notification())
                should_remove_job = True
                return
            logger.info("Checking CryptoBot payment status for invoice %s", payment_id)
            status = await cryptobot_service.check_payment(payment_id)
            logger.info("CryptoBot check_payment(%s) → %s", payment_id, status)
            if status == "paid":
                logger.info("Payment %s confirmed paid, updating balance", payment_id)
                await transactions_dao.update_status(payment_id, TransactionStatus.COMPLETED)
                await users_dao.increase_balance(user_id, amount)
                user = await users_dao.get_by_id(user_id)
                if user:
                    logger.info(
                        "Balance updated for user %s: +%.2f, new balance=%.2f",
                        user_id,
                        amount,
                        user.balance,
                    )
                    await bot_service.notify_user(
                        user_id, messages.payment_success_notification(amount, user.balance)
                    )
                    await bot_service.send_log_to_admin(messages.payment_admin_log(user, amount))
                else:
                    logger.error("User %s not found after balance increase!", user_id)
                should_remove_job = True
            else:
                logger.debug("Payment %s still not paid, will retry", payment_id)
    except Exception:
        logger.exception("Error in check_cryptobot_payment_status for payment_id=%s", payment_id)
        raise
    finally:
        if should_remove_job:
            try:
                scheduler.remove_job(f"check_payment_{payment_id}")
                logger.info("Removed scheduler job check_payment_%s", payment_id)
            except JobLookupError:
                logger.debug("Job check_payment_%s already removed", payment_id)
