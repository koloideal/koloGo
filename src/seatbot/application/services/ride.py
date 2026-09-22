from datetime import datetime, timedelta

from seatbot.application.services.bot import BotService
from seatbot.domain.exceptions import (AlreadyBookedError, NoFreeSeatsError,
                                       RideNotBookableError, UserBannedError,
                                       VipHoldActiveError)
from seatbot.domain.schemas import (Booking, BookingStatus, Ride, RideStatus,
                                    TransactionType, User)
from seatbot.infrastructure.database.dao import (BookingsDAO, RidesDAO, TransactionsDAO,
                                                 UsersDAO)
from seatbot.infrastructure.notifications import MessageBuilder
from seatbot.infrastructure.time import LocalClock


class RideService:
    def __init__(
        self,
        rides_dao: RidesDAO,
        bookings_dao: BookingsDAO,
        users_dao: UsersDAO,
        transactions_dao: TransactionsDAO,
        bot_service: BotService,
        message_builder: MessageBuilder,
        clock: LocalClock,
    ) -> None:
        self._rides_dao = rides_dao
        self._bookings_dao = bookings_dao
        self._users_dao = users_dao
        self._transactions_dao = transactions_dao
        self._bot_service = bot_service
        self._messages = message_builder
        self._clock = clock

    async def create_ride(
        self,
        departure_at: datetime,
        price: float,
        auto_approve: bool,
        seats_total: int = 4,
        note: str | None = None,
        is_visible: bool = True,
        repeat_days: int = 1,
        remind_minutes: int = 30,
        vip_hold_minutes: int = 0,
        origin: str | None = None,
        destination: str | None = None,
        template_ride_id: int | None = None,
    ) -> list[Ride]:
        rides = []
        for i in range(repeat_days):
            dep = departure_at + timedelta(days=i)
            ride = await self._rides_dao.create(
                departure_at=dep,
                price=price,
                seats_total=seats_total,
                auto_approve=auto_approve,
                note=note,
                is_visible=is_visible,
                remind_minutes=remind_minutes,
                vip_hold_minutes=vip_hold_minutes,
                origin=origin,
                destination=destination,
            )
            rides.append(ride)
        if template_ride_id is not None:
            await self._copy_vips_from_template(template_ride_id, rides)
        await self._notify_new_rides(rides)
        return rides

    async def create_ride_from_template(
        self,
        template_ride_id: int,
        start_date: datetime,
        repeat_days: int = 1,
    ) -> list[Ride] | None:
        template = await self._rides_dao.get_by_id(template_ride_id)
        if not template:
            return None
        local_dep = self._clock.to_local(template.departure_at)
        local_start = self._clock.to_local(start_date)
        departure_at = self._clock.to_utc(
            local_start.replace(
                hour=local_dep.hour,
                minute=local_dep.minute,
                second=0,
                microsecond=0,
            )
        )
        return await self.create_ride(
            departure_at=departure_at,
            price=float(template.price),
            auto_approve=template.auto_approve,
            seats_total=template.seats_total,
            note=template.note,
            is_visible=template.is_visible,
            repeat_days=repeat_days,
            remind_minutes=template.remind_minutes,
            vip_hold_minutes=template.vip_hold_minutes,
            origin=template.origin,
            destination=template.destination,
            template_ride_id=template_ride_id,
        )

    async def _copy_vips_from_template(self, template_ride_id: int, rides: list[Ride]) -> None:
        bookings = await self._bookings_dao.list_for_ride_with_status(
            template_ride_id, {BookingStatus.APPROVED}
        )
        vip_ids: list[int] = []
        for b in bookings:
            user = await self._users_dao.get_by_id(b.user_id)
            if user and user.is_vip and b.user_id not in vip_ids:
                vip_ids.append(b.user_id)
        for ride in rides:
            for vip_id in vip_ids:
                await self.add_passenger(ride.ride_id, vip_id)

    async def _notify_new_rides(self, rides: list[Ride]) -> None:
        subscribers = await self._users_dao.list_new_ride_subscribers()
        for ride in rides:
            if not ride.is_visible:
                continue
            message = self._messages.new_ride_notification(ride)
            for user in subscribers:
                await self._bot_service.notify_user(user.user_id, message)

    async def cancel_ride(self, ride_id: int) -> Ride | None:
        ride = await self._rides_dao.get_by_id(ride_id)
        if not ride:
            return None
        await self._rides_dao.set_status(ride_id, RideStatus.CANCELLED)

        active_bookings = await self._bookings_dao.list_for_ride_with_status(
            ride_id, {BookingStatus.PENDING, BookingStatus.APPROVED}
        )
        for booking in active_bookings:
            await self._bookings_dao.set_status(booking.booking_id, BookingStatus.CANCELLED)
            if booking.paid_amount > 0:
                await self._users_dao.increase_balance(booking.user_id, booking.paid_amount)
                await self._transactions_dao.create(
                    user_id=booking.user_id,
                    amount=booking.paid_amount,
                    type=TransactionType.REFUND,
                    ride_id=ride_id,
                )
            await self._bot_service.notify_user(
                booking.user_id,
                self._messages.booking_cancelled_by_admin_notification(ride, booking.paid_amount),
            )
        return await self._rides_dao.get_by_id(ride_id)

    async def change_ride_time(self, ride_id: int, hour: int, minute: int) -> Ride | None:
        ride = await self._rides_dao.get_by_id_for_update(ride_id)
        if not ride or ride.status not in (RideStatus.OPEN, RideStatus.CLOSED):
            return None
        old_departure = ride.departure_at
        local_old = self._clock.to_local(old_departure)
        new_departure = self._clock.to_utc(
            local_old.replace(hour=hour, minute=minute, second=0, microsecond=0)
        )
        if new_departure == old_departure:
            return ride
        await self._rides_dao.set_departure_at(ride_id, new_departure)
        updated = await self._rides_dao.get_by_id(ride_id)
        if not updated:
            return None
        approved = await self._bookings_dao.list_for_ride_with_status(
            ride_id, {BookingStatus.APPROVED}
        )
        for booking in approved:
            await self._bot_service.notify_user(
                booking.user_id,
                self._messages.ride_time_changed_notification(updated, old_departure),
            )
        await self._bot_service.send_log_to_admin(
            self._messages.ride_time_changed_admin_log(updated, old_departure, len(approved))
        )
        now = self._clock.now()
        if updated.remind_minutes > 0:
            remind_at = new_departure - timedelta(minutes=updated.remind_minutes)
            if now >= remind_at and now <= new_departure + timedelta(minutes=30):
                for booking in approved:
                    await self._bot_service.notify_user(
                        booking.user_id, self._messages.ride_reminder_notification(updated)
                    )
                await self._bot_service.send_log_to_admin(
                    self._messages.ride_reminder_admin_notification(updated, len(approved))
                )
                await self._rides_dao.mark_remind_sent(ride_id)
        return updated

    async def complete_ride(self, ride_id: int) -> Ride | None:
        ride = await self._rides_dao.get_by_id(ride_id)
        if not ride:
            return None
        await self._rides_dao.set_status(ride_id, RideStatus.COMPLETED)
        approved = await self._bookings_dao.list_for_ride_with_status(ride_id, {BookingStatus.APPROVED})
        for booking in approved:
            user = await self._users_dao.get_by_id(booking.user_id)
            is_free = ride.is_free or bool(user and user.is_vip)
            price = float(ride.price)
            if not is_free and user and user.balance >= price:
                await self._users_dao.decrease_balance(booking.user_id, price)
                await self._transactions_dao.create(
                    user_id=booking.user_id,
                    amount=price,
                    type=TransactionType.RIDE_PAYMENT,
                    ride_id=ride_id,
                )
                await self._bookings_dao.set_paid_amount(booking.booking_id, price)
            await self._bookings_dao.set_status(booking.booking_id, BookingStatus.COMPLETED)
            updated = await self._bookings_dao.get_by_id(booking.booking_id)
            paid = updated.paid_amount if updated else 0.0
            await self._bot_service.notify_user(
                booking.user_id, self._messages.ride_completed_notification(ride, paid, price, is_free)
            )
        pending = await self._bookings_dao.list_for_ride_with_status(ride_id, {BookingStatus.PENDING})
        for booking in pending:
            await self._bookings_dao.set_status(booking.booking_id, BookingStatus.CANCELLED)
        return await self._rides_dao.get_by_id(ride_id)

    async def mark_no_show(self, booking_id: int) -> Booking | None:
        booking = await self._bookings_dao.get_by_id_for_update(booking_id)
        if not booking or booking.status != BookingStatus.APPROVED:
            return None
        await self._bookings_dao.set_status(booking_id, BookingStatus.NO_SHOW)
        ride = await self._rides_dao.get_by_id(booking.ride_id)
        if ride:
            await self._bot_service.notify_user(booking.user_id, self._messages.no_show_notification(ride))
        return await self._bookings_dao.get_by_id(booking_id)

    async def kick_booking(self, booking_id: int, reason: str) -> Booking | None:
        booking = await self._bookings_dao.get_by_id_for_update(booking_id)
        if not booking or booking.status not in (BookingStatus.PENDING, BookingStatus.APPROVED):
            return None
        await self._bookings_dao.set_status(booking_id, BookingStatus.CANCELLED)
        if booking.paid_amount > 0:
            await self._users_dao.increase_balance(booking.user_id, booking.paid_amount)
            await self._transactions_dao.create(
                user_id=booking.user_id,
                amount=booking.paid_amount,
                type=TransactionType.REFUND,
                ride_id=booking.ride_id,
            )
        ride = await self._rides_dao.get_by_id(booking.ride_id)
        if ride:
            await self._bot_service.notify_user(
                booking.user_id, self._messages.booking_kicked_notification(ride, reason)
            )
        return await self._bookings_dao.get_by_id(booking_id)

    async def broadcast_ride(self, ride_id: int, text: str) -> int:
        ride = await self._rides_dao.get_by_id(ride_id)
        if not ride:
            return 0
        approved = await self._bookings_dao.list_for_ride_with_status(ride_id, {BookingStatus.APPROVED})
        sent = 0
        for booking in approved:
            ok = await self._bot_service.notify_user(booking.user_id, text)
            if ok:
                sent += 1
        return sent

    async def book_ride(self, ride_id: int, user: User) -> Booking:
        ride = await self._rides_dao.get_by_id_for_update(ride_id)
        if not ride:
            raise RideNotBookableError(ride_id, "поездка не найдена")
        if ride.status != RideStatus.OPEN:
            raise RideNotBookableError(ride_id, f"статус {ride.status.value}")
        if ride.departure_at <= self._clock.now():
            raise RideNotBookableError(ride_id, "поездка уже в прошлом")

        if user.is_banned:
            raise UserBannedError(user.user_id)

        if ride.is_vip_hold_active(self._clock.now()) and not user.is_vip:
            raise VipHoldActiveError(ride_id, ride.vip_hold_remaining_seconds(self._clock.now()))

        existing = await self._bookings_dao.get_by_ride_and_user(ride_id, user.user_id)
        if existing:
            raise AlreadyBookedError(ride_id, user.user_id)

        active_count = await self._bookings_dao.count_active_for_ride(ride_id)
        if active_count >= ride.seats_total:
            raise NoFreeSeatsError(ride_id)

        is_vip = user.is_vip
        is_free = ride.is_free or is_vip
        ride_price = float(ride.price)

        booking = await self._bookings_dao.create(
            ride_id=ride_id,
            user_id=user.user_id,
            paid_amount=0.0,
        )

        if ride.auto_approve or is_vip:
            await self._bookings_dao.set_status(booking.booking_id, BookingStatus.APPROVED)
            updated = await self._bookings_dao.get_by_id(booking.booking_id)
            if updated:
                booking = updated
            due_amount = 0.0 if is_free else ride_price
            await self._bot_service.notify_user(
                user.user_id, self._messages.booking_approved_notification(ride, due_amount)
            )

        await self._bot_service.send_log_to_admin(
            self._messages.new_booking_admin_log(booking, user, ride),
            reply_markup=(
                self._messages.booking_approve_keyboard(booking.booking_id)
                if booking.status == BookingStatus.PENDING
                else None
            ),
        )
        return booking

    async def add_passenger(self, ride_id: int, user_id: int) -> Booking | None:
        ride = await self._rides_dao.get_by_id_for_update(ride_id)
        if not ride or ride.status != RideStatus.OPEN:
            return None
        user = await self._users_dao.get_by_id(user_id)
        if not user:
            return None
        existing = await self._bookings_dao.get_by_ride_and_user(ride_id, user_id)
        if existing:
            return existing
        active_count = await self._bookings_dao.count_active_for_ride(ride_id)
        if active_count >= ride.seats_total:
            raise NoFreeSeatsError(ride_id)

        is_free = ride.is_free or user.is_vip
        ride_price = float(ride.price)

        booking = await self._bookings_dao.create(
            ride_id=ride_id,
            user_id=user_id,
            paid_amount=0.0,
        )
        await self._bookings_dao.set_status(booking.booking_id, BookingStatus.APPROVED)
        due_amount = 0.0 if is_free else ride_price
        await self._bot_service.notify_user(
            user_id, self._messages.added_by_admin_notification(ride, due_amount)
        )
        return await self._bookings_dao.get_by_id(booking.booking_id)

    async def approve_booking(self, booking_id: int) -> Booking | None:
        booking = await self._bookings_dao.get_by_id_for_update(booking_id)
        if not booking or booking.status != BookingStatus.PENDING:
            return None
        await self._bookings_dao.set_status(booking_id, BookingStatus.APPROVED)
        ride = await self._rides_dao.get_by_id(booking.ride_id)
        if ride:
            user = await self._users_dao.get_by_id(booking.user_id)
            due_amount = (
                0.0 if ride.is_free or (user and user.is_vip) else float(ride.price) - booking.paid_amount
            )
            await self._bot_service.notify_user(
                booking.user_id, self._messages.booking_approved_notification(ride, due_amount)
            )
        return await self._bookings_dao.get_by_id(booking_id)

    async def reject_booking(self, booking_id: int) -> Booking | None:
        booking = await self._bookings_dao.get_by_id_for_update(booking_id)
        if not booking or booking.status != BookingStatus.PENDING:
            return None
        await self._bookings_dao.set_status(booking_id, BookingStatus.REJECTED)
        ride = await self._rides_dao.get_by_id(booking.ride_id)
        if ride:
            await self._bot_service.notify_user(
                booking.user_id, self._messages.booking_rejected_notification(ride, booking.paid_amount)
            )
        return await self._bookings_dao.get_by_id(booking_id)

    async def cancel_booking_by_user(self, booking_id: int, user_id: int) -> Booking | None:
        booking = await self._bookings_dao.get_by_id_for_update(booking_id)
        if not booking or booking.user_id != user_id:
            return None
        if booking.status not in (BookingStatus.PENDING, BookingStatus.APPROVED):
            return None
        await self._bookings_dao.set_status(booking_id, BookingStatus.CANCELLED)
        if booking.paid_amount > 0:
            await self._users_dao.increase_balance(user_id, booking.paid_amount)
            await self._transactions_dao.create(
                user_id=user_id,
                amount=booking.paid_amount,
                type=TransactionType.REFUND,
                ride_id=booking.ride_id,
            )
        ride = await self._rides_dao.get_by_id(booking.ride_id)
        user = await self._users_dao.get_by_id(user_id)
        if ride and user:
            await self._bot_service.send_log_to_admin(
                self._messages.booking_cancelled_by_user_admin_log(booking, user, ride)
            )
        return await self._bookings_dao.get_by_id(booking_id)
