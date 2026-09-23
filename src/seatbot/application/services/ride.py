from datetime import datetime, timedelta

from seatbot.application.services.bot import BotService
from seatbot.domain.exceptions import (AlreadyBookedError, NoFreeSeatsError,
                                       RideInPastError, RideNotBookableError,
                                       SeatBotError, UserBannedError, VipHoldActiveError)
from seatbot.domain.schemas import (Booking, BookingStatus, Ride, RideStatus,
                                    TransactionType, User)
from seatbot.infrastructure.database.dao import (BookingsDAO, RidesDAO, TrackPointsDAO,
                                                 TransactionsDAO, UsersDAO)
from seatbot.infrastructure.geo import GeoService
from seatbot.infrastructure.notifications import MessageBuilder
from seatbot.infrastructure.time import LocalClock

_ACTIVE_RIDE_STATUSES = (RideStatus.OPEN, RideStatus.CLOSED, RideStatus.IN_PROGRESS)


class RideService:
    def __init__(
        self,
        rides_dao: RidesDAO,
        bookings_dao: BookingsDAO,
        users_dao: UsersDAO,
        transactions_dao: TransactionsDAO,
        track_dao: TrackPointsDAO,
        bot_service: BotService,
        message_builder: MessageBuilder,
        clock: LocalClock,
        geo: GeoService,
    ) -> None:
        self._rides_dao = rides_dao
        self._bookings_dao = bookings_dao
        self._users_dao = users_dao
        self._transactions_dao = transactions_dao
        self._track_dao = track_dao
        self._bot_service = bot_service
        self._messages = message_builder
        self._clock = clock
        self._geo = geo

    async def create_ride(
        self,
        departure_at: datetime,
        price: float,
        auto_approve: bool,
        origin: str,
        destination: str,
        seats_total: int = 4,
        note: str | None = None,
        is_visible: bool = True,
        repeat_days: int = 1,
        remind_minutes: int = 30,
        vip_hold_minutes: int = 0,
        origin_lat: float | None = None,
        origin_lon: float | None = None,
        destination_lat: float | None = None,
        destination_lon: float | None = None,
        template_ride_id: int | None = None,
    ) -> list[Ride]:
        if departure_at <= self._clock.now():
            raise RideInPastError(departure_at)
        local_departure = self._clock.to_local(departure_at)
        rides = []
        for i in range(repeat_days):
            dep = self._clock.to_utc(local_departure + timedelta(days=i))
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
                origin_lat=origin_lat,
                origin_lon=origin_lon,
                destination_lat=destination_lat,
                destination_lon=destination_lon,
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
            origin_lat=template.origin_lat,
            origin_lon=template.origin_lon,
            destination_lat=template.destination_lat,
            destination_lon=template.destination_lon,
            template_ride_id=template_ride_id,
        )

    async def _copy_vips_from_template(self, template_ride_id: int, rides: list[Ride]) -> None:
        bookings = await self._bookings_dao.list_for_ride_with_status(
            template_ride_id, {BookingStatus.APPROVED}
        )
        vip_ids: list[int] = []
        for b in bookings:
            user = await self._users_dao.get_by_id(b.user_id)
            if user and user.is_vip and not user.is_banned and b.user_id not in vip_ids:
                vip_ids.append(b.user_id)
        for ride in rides:
            for vip_id in vip_ids:
                try:
                    await self.add_passenger(ride.ride_id, vip_id, notify=ride.is_visible)
                except NoFreeSeatsError:
                    break

    async def _notify_new_rides(self, rides: list[Ride]) -> None:
        visible = [ride for ride in rides if ride.is_visible]
        if not visible:
            return
        message = (
            self._messages.new_ride_notification(visible[0])
            if len(visible) == 1
            else self._messages.new_rides_notification(visible)
        )
        markup = self._messages.book_rides_keyboard(visible)
        for user in await self._users_dao.list_new_ride_subscribers():
            await self._bot_service.notify_user(user.user_id, message, reply_markup=markup)

    async def cancel_ride(self, ride_id: int) -> Ride | None:
        ride = await self._rides_dao.get_by_id_for_update(ride_id)
        if not ride or ride.status not in _ACTIVE_RIDE_STATUSES:
            return None
        await self._rides_dao.set_status(ride_id, RideStatus.CANCELLED)
        await self._rides_dao.stop_live(ride_id)

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
        if new_departure <= self._clock.now():
            raise RideInPastError(new_departure)
        await self._rides_dao.set_departure_at(ride_id, new_departure)
        if ride.status == RideStatus.CLOSED:
            await self._rides_dao.set_status(ride_id, RideStatus.OPEN)
        updated = await self._rides_dao.get_by_id(ride_id)
        if not updated:
            return None
        affected = await self._bookings_dao.list_for_ride_with_status(
            ride_id, {BookingStatus.APPROVED, BookingStatus.PENDING}
        )
        for booking in affected:
            await self._bot_service.notify_user(
                booking.user_id,
                self._messages.ride_time_changed_notification(updated, old_departure),
                reply_markup=self._messages.origin_keyboard(updated),
            )
        approved = [b for b in affected if b.status == BookingStatus.APPROVED]
        await self._bot_service.send_log_to_admin(
            self._messages.ride_time_changed_admin_log(updated, old_departure, len(approved))
        )
        now = self._clock.now()
        if updated.remind_minutes > 0:
            remind_at = new_departure - timedelta(minutes=updated.remind_minutes)
            if now >= remind_at and now <= new_departure + timedelta(minutes=30):
                for booking in approved:
                    await self._bot_service.notify_user(
                        booking.user_id,
                        self._messages.ride_reminder_notification(updated),
                        reply_markup=self._messages.origin_keyboard(updated),
                    )
                await self._bot_service.send_log_to_admin(
                    self._messages.ride_reminder_admin_notification(updated, len(approved))
                )
                await self._rides_dao.mark_remind_sent(ride_id)
        return updated

    async def complete_ride(self, ride_id: int) -> Ride | None:
        ride = await self._rides_dao.get_by_id_for_update(ride_id)
        if not ride or ride.status not in _ACTIVE_RIDE_STATUSES:
            return None
        await self._rides_dao.set_awaiting_live(ride_id, False)
        if ride.finished_at is None:
            await self._rides_dao.set_finished_at(ride_id, self._clock.now())
        await self._rides_dao.set_status(ride_id, RideStatus.COMPLETED)
        ride = (await self._rides_dao.get_by_id(ride_id)) or ride
        points = await self._track_dao.list_for_ride(ride_id)
        map_url = self._geo.yandex_route_url(points) if len(points) >= 2 else None
        map_markup = self._messages.ride_map_keyboard(map_url) if map_url else None
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
                booking.user_id,
                self._messages.ride_completed_notification(ride, paid, price, is_free),
                reply_markup=map_markup,
            )
        pending = await self._bookings_dao.list_for_ride_with_status(ride_id, {BookingStatus.PENDING})
        for booking in pending:
            await self._bookings_dao.set_status(booking.booking_id, BookingStatus.CANCELLED)
        final = await self._rides_dao.get_by_id(ride_id)
        if final:
            await self._bot_service.send_log_to_admin(
                self._messages.ride_completed_admin_log(final, len(approved)),
                reply_markup=map_markup,
            )
        return final

    def can_mark_no_show(self, ride: Ride) -> bool:
        return ride.status in _ACTIVE_RIDE_STATUSES and (
            ride.status != RideStatus.OPEN or ride.departure_at <= self._clock.now()
        )

    async def mark_no_show(self, booking_id: int) -> Booking | None:
        booking = await self._bookings_dao.get_by_id_for_update(booking_id)
        if not booking or booking.status != BookingStatus.APPROVED:
            return None
        ride = await self._rides_dao.get_by_id(booking.ride_id)
        if not ride or not self.can_mark_no_show(ride):
            return None
        await self._bookings_dao.set_status(booking_id, BookingStatus.NO_SHOW)
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

    async def booking_error(self, ride: Ride, user: User) -> SeatBotError | None:
        now = self._clock.now()
        if ride.status != RideStatus.OPEN:
            return RideNotBookableError(ride.ride_id, "запись на поездку закрыта")
        if ride.departure_at <= now:
            return RideNotBookableError(ride.ride_id, "поездка уже отправилась")
        if not ride.is_visible:
            return RideNotBookableError(ride.ride_id, "поездка недоступна для брони")
        if user.is_banned:
            return UserBannedError(user.user_id)
        if await self._bookings_dao.get_by_ride_and_user(ride.ride_id, user.user_id):
            return AlreadyBookedError(ride.ride_id, user.user_id)
        if await self._bookings_dao.exists_with_status(ride.ride_id, user.user_id, BookingStatus.REJECTED):
            return RideNotBookableError(ride.ride_id, "водитель уже отклонил вашу бронь на эту поездку")
        if ride.is_vip_hold_active(now) and not user.is_vip:
            return VipHoldActiveError(ride.ride_id, ride.vip_hold_remaining_seconds(now))
        if await self._bookings_dao.count_approved_for_ride(ride.ride_id) >= ride.seats_total:
            return NoFreeSeatsError(ride.ride_id)
        return None

    async def _reject_overflow(self, ride: Ride) -> int:
        if await self._bookings_dao.count_approved_for_ride(ride.ride_id) < ride.seats_total:
            return 0
        pending = await self._bookings_dao.list_for_ride_with_status(ride.ride_id, {BookingStatus.PENDING})
        for booking in pending:
            await self._bookings_dao.set_status(booking.booking_id, BookingStatus.CANCELLED)
            await self._bot_service.notify_user(
                booking.user_id, self._messages.booking_rejected_no_seats_notification(ride)
            )
        return len(pending)

    async def book_ride(self, ride_id: int, user: User) -> Booking:
        ride = await self._rides_dao.get_by_id_for_update(ride_id)
        if not ride:
            raise RideNotBookableError(ride_id, "поездка не найдена")
        error = await self.booking_error(ride, user)
        if error:
            raise error

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
                user.user_id,
                self._messages.booking_approved_notification(ride, due_amount),
                reply_markup=self._messages.origin_keyboard(ride),
            )
            await self._reject_overflow(ride)

        await self._bot_service.send_log_to_admin(
            self._messages.new_booking_admin_log(booking, user, ride),
            reply_markup=(
                self._messages.booking_approve_keyboard(booking.booking_id)
                if booking.status == BookingStatus.PENDING
                else None
            ),
        )
        return booking

    async def add_passenger(self, ride_id: int, user_id: int, notify: bool = True) -> Booking | None:
        ride = await self._rides_dao.get_by_id_for_update(ride_id)
        if not ride or ride.status != RideStatus.OPEN:
            return None
        user = await self._users_dao.get_by_id(user_id)
        if not user:
            return None
        existing = await self._bookings_dao.get_by_ride_and_user(ride_id, user_id)
        if existing:
            return existing
        if await self._bookings_dao.count_approved_for_ride(ride_id) >= ride.seats_total:
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
        if notify:
            await self._bot_service.notify_user(
                user_id,
                self._messages.added_by_admin_notification(ride, due_amount),
                reply_markup=self._messages.origin_keyboard(ride),
            )
        await self._reject_overflow(ride)
        return await self._bookings_dao.get_by_id(booking.booking_id)

    async def set_visibility(self, ride_id: int, is_visible: bool) -> Ride | None:
        ride = await self._rides_dao.get_by_id_for_update(ride_id)
        if not ride or ride.status != RideStatus.OPEN or ride.is_visible == is_visible:
            return ride
        updated = await self._rides_dao.set_visibility(ride_id, is_visible)
        if updated and is_visible and updated.departure_at > self._clock.now():
            await self._notify_new_rides([updated])
        return updated

    async def set_auto_approve(self, ride_id: int, auto_approve: bool) -> int:
        ride = await self._rides_dao.get_by_id_for_update(ride_id)
        if not ride or ride.status != RideStatus.OPEN:
            return 0
        await self._rides_dao.set_auto_approve(ride_id, auto_approve)
        if not auto_approve:
            return 0
        pending = await self._bookings_dao.list_for_ride_with_status(ride_id, {BookingStatus.PENDING})
        approved = 0
        for booking in pending:
            try:
                if await self.approve_booking(booking.booking_id):
                    approved += 1
            except NoFreeSeatsError:
                break
        return approved

    async def approve_booking(self, booking_id: int) -> Booking | None:
        current = await self._bookings_dao.get_by_id(booking_id)
        if not current:
            return None
        ride = await self._rides_dao.get_by_id_for_update(current.ride_id)
        booking = await self._bookings_dao.get_by_id_for_update(booking_id)
        if not ride or not booking or booking.status != BookingStatus.PENDING:
            return None
        if await self._bookings_dao.count_approved_for_ride(ride.ride_id) >= ride.seats_total:
            raise NoFreeSeatsError(ride.ride_id)
        await self._bookings_dao.set_status(booking_id, BookingStatus.APPROVED)
        user = await self._users_dao.get_by_id(booking.user_id)
        due_amount = (
            0.0 if ride.is_free or (user and user.is_vip) else float(ride.price) - booking.paid_amount
        )
        await self._bot_service.notify_user(
            booking.user_id,
            self._messages.booking_approved_notification(ride, due_amount),
            reply_markup=self._messages.origin_keyboard(ride),
        )
        await self._reject_overflow(ride)
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

    def can_user_cancel(self, booking: Booking, ride: Ride) -> bool:
        if booking.status == BookingStatus.PENDING:
            return ride.status in (RideStatus.OPEN, RideStatus.CLOSED)
        if booking.status == BookingStatus.APPROVED:
            return ride.status == RideStatus.OPEN and ride.departure_at > self._clock.now()
        return False

    async def cancel_booking_by_user(self, booking_id: int, user_id: int) -> Booking | None:
        booking = await self._bookings_dao.get_by_id_for_update(booking_id)
        if not booking or booking.user_id != user_id:
            return None
        ride = await self._rides_dao.get_by_id(booking.ride_id)
        if not ride or not self.can_user_cancel(booking, ride):
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
        user = await self._users_dao.get_by_id(user_id)
        if user:
            await self._bot_service.send_log_to_admin(
                self._messages.booking_cancelled_by_user_admin_log(booking, user, ride)
            )
        return await self._bookings_dao.get_by_id(booking_id)
