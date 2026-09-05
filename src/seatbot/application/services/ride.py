from datetime import UTC, datetime, timedelta

from seatbot.application.services.bot import BotService
from seatbot.domain.exceptions import (AlreadyBookedError, NoFreeSeatsError,
                                       RideNotBookableError, UserBannedError)
from seatbot.domain.schemas import (Booking, BookingStatus, Ride, RideStatus,
                                    TransactionType, User)
from seatbot.infrastructure.database.dao import (BookingsDAO, RidesDAO, TransactionsDAO,
                                                 UsersDAO)
from seatbot.infrastructure.notifications import MessageBuilder


class RideService:
    def __init__(
        self,
        rides_dao: RidesDAO,
        bookings_dao: BookingsDAO,
        users_dao: UsersDAO,
        transactions_dao: TransactionsDAO,
        bot_service: BotService,
    ) -> None:
        self._rides_dao = rides_dao
        self._bookings_dao = bookings_dao
        self._users_dao = users_dao
        self._transactions_dao = transactions_dao
        self._bot_service = bot_service

    # ── создание/управление поездками ────────────────────────────────────────

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
    ) -> list[Ride]:
        """Создаёт поездку. Если repeat_days > 1, создаёт несколько подряд."""
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
            )
            rides.append(ride)
        return rides

    async def create_ride_from_template(
        self,
        template_ride_id: int,
        start_date: datetime,
        repeat_days: int = 1,
    ) -> list[Ride] | None:
        """Создаёт поездки из шаблона (прошлой поездки), меняя только дату."""
        template = await self._rides_dao.get_by_id(template_ride_id)
        if not template:
            return None
        departure_at = start_date.replace(
            hour=template.departure_at.hour,
            minute=template.departure_at.minute,
            second=0,
            microsecond=0,
            tzinfo=UTC,
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
        )

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
                MessageBuilder.booking_cancelled_by_admin_notification(ride),
            )
        return await self._rides_dao.get_by_id(ride_id)

    async def complete_ride(self, ride_id: int) -> Ride | None:
        ride = await self._rides_dao.get_by_id(ride_id)
        if not ride:
            return None
        await self._rides_dao.set_status(ride_id, RideStatus.COMPLETED)
        approved = await self._bookings_dao.list_for_ride_with_status(
            ride_id, {BookingStatus.APPROVED}
        )
        for booking in approved:
            await self._bookings_dao.set_status(booking.booking_id, BookingStatus.COMPLETED)
            await self._bot_service.notify_user(
                booking.user_id, MessageBuilder.ride_completed_notification(ride)
            )
        pending = await self._bookings_dao.list_for_ride_with_status(
            ride_id, {BookingStatus.PENDING}
        )
        for booking in pending:
            await self._bookings_dao.set_status(booking.booking_id, BookingStatus.CANCELLED)
            if booking.paid_amount > 0:
                await self._users_dao.increase_balance(booking.user_id, booking.paid_amount)
                await self._transactions_dao.create(
                    user_id=booking.user_id,
                    amount=booking.paid_amount,
                    type=TransactionType.REFUND,
                    ride_id=ride_id,
                )
        return await self._rides_dao.get_by_id(ride_id)

    async def mark_no_show(self, booking_id: int) -> Booking | None:
        booking = await self._bookings_dao.get_by_id(booking_id)
        if not booking:
            return None
        await self._bookings_dao.set_status(booking_id, BookingStatus.NO_SHOW)
        ride = await self._rides_dao.get_by_id(booking.ride_id)
        if ride:
            await self._bot_service.notify_user(
                booking.user_id, MessageBuilder.no_show_notification(ride)
            )
        return await self._bookings_dao.get_by_id(booking_id)

    # ── бронирование ──────────────────────────────────────────────────────────

    async def book_ride(self, ride_id: int, user: User) -> Booking:
        ride = await self._rides_dao.get_by_id(ride_id)
        if not ride:
            raise RideNotBookableError(ride_id, "поездка не найдена")
        if ride.status != RideStatus.OPEN:
            raise RideNotBookableError(ride_id, f"статус {ride.status.value}")
        if ride.departure_at <= datetime.now(UTC):
            raise RideNotBookableError(ride_id, "поездка уже в прошлом")

        if user.is_banned:
            raise UserBannedError(user.user_id)

        existing = await self._bookings_dao.get_by_ride_and_user(ride_id, user.user_id)
        if existing:
            raise AlreadyBookedError(ride_id, user.user_id)

        active_count = await self._bookings_dao.count_active_for_ride(ride_id)
        if active_count >= ride.seats_total:
            raise NoFreeSeatsError(ride_id)

        is_vip = user.is_vip
        is_free = ride.is_free or is_vip
        ride_price = float(ride.price)

        # Депозит — только для предоплаты. Если баланса не хватает,
        # бронь всё равно создаётся (налик при встрече), paid_amount=0.
        # С депозита списываем только если баланс покрывает полную цену.
        if is_free:
            paid_amount = 0.0
        elif user.balance >= ride_price:
            paid_amount = ride_price
        else:
            # Налик — ничего не списываем
            paid_amount = 0.0

        if paid_amount > 0:
            await self._users_dao.decrease_balance(user.user_id, paid_amount)
            await self._transactions_dao.create(
                user_id=user.user_id,
                amount=paid_amount,
                type=TransactionType.RIDE_PAYMENT,
                ride_id=ride_id,
            )

        booking = await self._bookings_dao.create(
            ride_id=ride_id,
            user_id=user.user_id,
            paid_amount=paid_amount,
        )

        if ride.auto_approve or is_vip:
            await self._bookings_dao.set_status(booking.booking_id, BookingStatus.APPROVED)
            updated = await self._bookings_dao.get_by_id(booking.booking_id)
            if updated:
                booking = updated
            await self._bot_service.notify_user(
                user.user_id, MessageBuilder.booking_approved_notification(ride)
            )

        await self._bot_service.send_log_to_admin(
            MessageBuilder.new_booking_admin_log(booking, user, ride)
        )
        return booking

    # ── ручное добавление пассажира админом ───────────────────────────────────

    async def add_passenger(self, ride_id: int, user_id: int) -> Booking | None:
        """Админ вручную добавляет клиента в поездку (сразу approved, бесплатно)."""
        ride = await self._rides_dao.get_by_id(ride_id)
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
        booking = await self._bookings_dao.create(
            ride_id=ride_id,
            user_id=user_id,
            paid_amount=0.0,
        )
        await self._bookings_dao.set_status(booking.booking_id, BookingStatus.APPROVED)
        await self._bot_service.notify_user(
            user_id, MessageBuilder.added_by_admin_notification(ride)
        )
        return await self._bookings_dao.get_by_id(booking.booking_id)

    # ── апрув / реджект ───────────────────────────────────────────────────────

    async def approve_booking(self, booking_id: int) -> Booking | None:
        booking = await self._bookings_dao.get_by_id(booking_id)
        if not booking or booking.status != BookingStatus.PENDING:
            return None
        await self._bookings_dao.set_status(booking_id, BookingStatus.APPROVED)
        ride = await self._rides_dao.get_by_id(booking.ride_id)
        if ride:
            await self._bot_service.notify_user(
                booking.user_id, MessageBuilder.booking_approved_notification(ride)
            )
        return await self._bookings_dao.get_by_id(booking_id)

    async def reject_booking(self, booking_id: int) -> Booking | None:
        booking = await self._bookings_dao.get_by_id(booking_id)
        if not booking or booking.status != BookingStatus.PENDING:
            return None
        await self._bookings_dao.set_status(booking_id, BookingStatus.REJECTED)
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
                booking.user_id, MessageBuilder.booking_rejected_notification(ride)
            )
        return await self._bookings_dao.get_by_id(booking_id)

    async def cancel_booking_by_user(self, booking_id: int, user_id: int) -> Booking | None:
        booking = await self._bookings_dao.get_by_id(booking_id)
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
        return await self._bookings_dao.get_by_id(booking_id)
