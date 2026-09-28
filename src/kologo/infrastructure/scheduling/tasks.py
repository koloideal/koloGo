import logging
from datetime import timedelta

import aiohttp
from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dishka import AsyncContainer

from kologo.application.services.bot import BotService
from kologo.application.services.ride import RideService
from kologo.application.services.tracking import TrackingService
from kologo.domain.schemas import BookingStatus, RideStatus, TransactionStatus
from kologo.infrastructure.config.models import TrackingConfig
from kologo.infrastructure.database.dao import BookingsDAO, RidesDAO
from kologo.infrastructure.notifications import MessageBuilder
from kologo.infrastructure.time import LocalClock

logger = logging.getLogger(__name__)


async def auto_close_past_rides(container: AsyncContainer) -> None:
    async with container() as scope:
        rides_dao: RidesDAO = await scope.get(RidesDAO)
        bookings_dao: BookingsDAO = await scope.get(BookingsDAO)
        ride_service: RideService = await scope.get(RideService)
        bot_service: BotService = await scope.get(BotService)
        messages: MessageBuilder = await scope.get(MessageBuilder)
        tracking: TrackingConfig = await scope.get(TrackingConfig)
        clock: LocalClock = await scope.get(LocalClock)

        now = clock.now()
        for ride in await rides_dao.list_open_departed(now - timedelta(minutes=30)):
            await rides_dao.set_status(ride.ride_id, RideStatus.CLOSED)
            await ride_service.invalidate_ride(ride.ride_id)
            approved = await bookings_dao.count_approved_for_ride(ride.ride_id)
            await bot_service.send_log_to_admin(
                messages.ride_not_started_admin_log(ride, approved, tracking.auto_complete_after_h),
                reply_markup=messages.ride_not_started_keyboard(ride.ride_id),
            )


async def auto_complete_stale_rides(container: AsyncContainer) -> None:
    async with container() as scope:
        rides_dao: RidesDAO = await scope.get(RidesDAO)
        ride_service: RideService = await scope.get(RideService)
        tracking: TrackingConfig = await scope.get(TrackingConfig)
        clock: LocalClock = await scope.get(LocalClock)

        before = clock.now() - timedelta(hours=tracking.auto_complete_after_h)
        for ride in await rides_dao.list_unfinished_departed(before):
            if await ride_service.complete_ride(ride.ride_id):
                logger.info("Auto-completed stale ride %s", ride.ride_id)


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


async def check_cryptobot_payment_status(payment_id: str, container: AsyncContainer) -> None:
    from kologo.application.services.payment import PaymentService

    try:
        async with container() as scope:
            payment_service: PaymentService = await scope.get(PaymentService)
            status = await payment_service.process_cryptobot_invoice(payment_id)
    except (aiohttp.ClientError, ConnectionError, TimeoutError):
        logger.warning("CryptoBot is unavailable, will retry payment_id=%s", payment_id, exc_info=True)
        return
    if status == TransactionStatus.PENDING:
        return
    logger.info("CryptoBot invoice %s finished with status=%s", payment_id, status)
    scheduler: AsyncIOScheduler = await container.get(AsyncIOScheduler)
    try:
        scheduler.remove_job(f"check_payment_{payment_id}")
    except JobLookupError:
        pass
