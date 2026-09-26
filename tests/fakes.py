from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from seatbot.application.services.bot import BotService
from seatbot.domain.exceptions import InsufficientBalanceError
from seatbot.domain.schemas import (Booking, BookingStatus, Ride, RideStatus,
                                    RideWithStats, Transaction, TransactionStatus,
                                    TransactionType, User)
from seatbot.infrastructure.cache.keys import CacheKey, CacheValue
from seatbot.infrastructure.cache.service import RedisService
from seatbot.infrastructure.database.dao.bookings_dao import BookingsDAO
from seatbot.infrastructure.database.dao.rides_dao import RidesDAO
from seatbot.infrastructure.database.dao.track_points_dao import TrackPointsDAO
from seatbot.infrastructure.database.dao.transactions_dao import TransactionsDAO
from seatbot.infrastructure.database.dao.users_dao import UsersDAO

NO_SESSION = cast(AsyncSession, None)


class FakeRidesDAO(RidesDAO):
    def __init__(self, bookings: "FakeBookingsDAO") -> None:
        super().__init__(NO_SESSION)
        self.rides: dict[int, Ride] = {}
        self._bookings = bookings

    def add(self, ride: Ride) -> Ride:
        self.rides[ride.ride_id] = ride
        return ride

    async def get_by_id(self, ride_id: int) -> Ride | None:
        return self.rides.get(ride_id)

    async def get_by_id_for_update(self, ride_id: int) -> Ride | None:
        return self.rides.get(ride_id)

    async def get_with_stats(self, ride_id: int) -> RideWithStats | None:
        ride = self.rides.get(ride_id)
        if not ride:
            return None
        return RideWithStats(
            ride=ride,
            booked_seats=len(
                await self._bookings.list_for_ride_with_status(ride_id, set(BookingStatus))
            ),
            approved_seats=await self._bookings.count_approved_for_ride(ride_id),
            pending_seats=len(
                await self._bookings.list_for_ride_with_status(ride_id, {BookingStatus.PENDING})
            ),
            finished_seats=len(
                await self._bookings.list_for_ride_with_status(
                    ride_id, {BookingStatus.COMPLETED, BookingStatus.NO_SHOW}
                )
            ),
        )

    async def set_status(self, ride_id: int, status: RideStatus) -> Ride | None:
        ride = self.rides.get(ride_id)
        if ride:
            ride.status = status
        return ride

    async def set_finished_at(self, ride_id: int, finished_at: datetime) -> None:
        if ride := self.rides.get(ride_id):
            ride.finished_at = finished_at

    async def set_awaiting_live(self, ride_id: int, value: bool) -> None:
        pass

    async def set_visibility(self, ride_id: int, is_visible: bool) -> Ride | None:
        ride = self.rides.get(ride_id)
        if ride:
            ride.is_visible = is_visible
        return ride

    async def set_auto_approve(self, ride_id: int, auto_approve: bool) -> Ride | None:
        ride = self.rides.get(ride_id)
        if ride:
            ride.auto_approve = auto_approve
        return ride

    async def set_departure_at(self, ride_id: int, departure_at: datetime) -> Ride | None:
        ride = self.rides.get(ride_id)
        if ride:
            ride.departure_at = departure_at
        return ride

    async def mark_remind_sent(self, ride_id: int) -> None:
        pass

    async def list_active(self) -> list[Ride]:
        return [
            r
            for r in self.rides.values()
            if r.status in (RideStatus.OPEN, RideStatus.CLOSED, RideStatus.IN_PROGRESS)
        ]

    async def list_upcoming_visible(self, now: datetime | None = None) -> list[RideWithStats]:
        now = now or datetime.now(UTC)
        result: list[RideWithStats] = []
        for ride in self.rides.values():
            if ride.is_visible and ride.status == RideStatus.OPEN and ride.departure_at > now:
                stats = await self.get_with_stats(ride.ride_id)
                if stats:
                    result.append(stats)
        return result

    async def get_in_progress(self) -> Ride | None:
        return next((r for r in self.rides.values() if r.status == RideStatus.IN_PROGRESS), None)

    async def list_templates(self, limit: int = 10) -> list[Ride]:
        return []


class FakeBookingsDAO(BookingsDAO):
    def __init__(self) -> None:
        super().__init__(NO_SESSION)
        self.bookings: dict[int, Booking] = {}
        self._next_id = 1

    def add(self, booking: Booking) -> Booking:
        self.bookings[booking.booking_id] = booking
        self._next_id = max(self._next_id, booking.booking_id + 1)
        return booking

    async def create(self, ride_id: int, user_id: int, paid_amount: float) -> Booking:
        booking = Booking(
            booking_id=self._next_id,
            ride_id=ride_id,
            user_id=user_id,
            status=BookingStatus.PENDING,
            paid_amount=paid_amount,
            created_at=datetime.now(UTC),
        )
        self.bookings[booking.booking_id] = booking
        self._next_id += 1
        return booking

    async def get_by_id(self, booking_id: int) -> Booking | None:
        return self.bookings.get(booking_id)

    async def get_by_id_for_update(self, booking_id: int) -> Booking | None:
        return self.bookings.get(booking_id)

    async def get_by_ride_and_user(
        self, ride_id: int, user_id: int, only_active: bool = True
    ) -> Booking | None:
        return next(
            (
                b
                for b in self.bookings.values()
                if b.ride_id == ride_id
                and b.user_id == user_id
                and (not only_active or b.status in (BookingStatus.PENDING, BookingStatus.APPROVED))
            ),
            None,
        )

    async def exists_with_status(self, ride_id: int, user_id: int, status: BookingStatus) -> bool:
        return any(
            b.ride_id == ride_id and b.user_id == user_id and b.status == status
            for b in self.bookings.values()
        )

    async def list_for_ride(self, ride_id: int, only_active: bool = False) -> list[Booking]:
        return [
            b
            for b in self.bookings.values()
            if b.ride_id == ride_id
            and (not only_active or b.status in (BookingStatus.PENDING, BookingStatus.APPROVED))
        ]

    async def list_for_ride_with_status(
        self, ride_id: int, statuses: set[BookingStatus]
    ) -> list[Booking]:
        return [b for b in self.bookings.values() if b.ride_id == ride_id and b.status in statuses]

    async def set_status(self, booking_id: int, status: BookingStatus) -> Booking | None:
        booking = self.bookings.get(booking_id)
        if booking:
            booking.status = status
        return booking

    async def set_paid_amount(self, booking_id: int, paid_amount: float) -> Booking | None:
        booking = self.bookings.get(booking_id)
        if booking:
            booking.paid_amount = paid_amount
        return booking

    async def count_approved_for_ride(self, ride_id: int) -> int:
        return len(await self.list_for_ride_with_status(ride_id, {BookingStatus.APPROVED}))

    async def status_counts_for_user(self, user_id: int) -> dict[BookingStatus, int]:
        counts: dict[BookingStatus, int] = {}
        for booking in self.bookings.values():
            if booking.user_id == user_id:
                counts[booking.status] = counts.get(booking.status, 0) + 1
        return counts

    async def list_for_user(self, user_id: int, limit: int = 50) -> list[Booking]:
        return [b for b in self.bookings.values() if b.user_id == user_id][:limit]

    async def next_active_for_user(self, user_id: int) -> Booking | None:
        return next(
            (
                b
                for b in self.bookings.values()
                if b.user_id == user_id and b.status in (BookingStatus.PENDING, BookingStatus.APPROVED)
            ),
            None,
        )


class FakeUsersDAO(UsersDAO):
    def __init__(self) -> None:
        super().__init__(NO_SESSION)
        self.users: dict[int, User] = {}

    def add(self, user: User) -> User:
        self.users[user.user_id] = user
        return user

    async def get_by_id(self, user_id: int) -> User | None:
        return self.users.get(user_id)

    async def increase_balance(self, user_id: int, amount: float) -> User | None:
        user = self.users.get(user_id)
        if not user:
            return None
        user.balance += amount
        return user

    async def decrease_balance(self, user_id: int, amount: float) -> User | None:
        user = self.users.get(user_id)
        if not user:
            return None
        if user.balance < amount:
            raise InsufficientBalanceError(required=amount, available=user.balance)
        user.balance -= amount
        return user


class FakeTransactionsDAO(TransactionsDAO):
    def __init__(self) -> None:
        super().__init__(NO_SESSION)
        self.transactions: list[Transaction] = []

    async def create(
        self,
        user_id: int,
        amount: float,
        type: TransactionType,
        ride_id: int | None = None,
        payment_id: str | None = None,
        payment_url: str | None = None,
        status: TransactionStatus = TransactionStatus.COMPLETED,
    ) -> Transaction:
        tx = Transaction(
            transaction_id=len(self.transactions) + 1,
            user_id=user_id,
            amount=amount,
            type=type,
            ride_id=ride_id,
            created_at=datetime.now(UTC),
            payment_id=payment_id,
            payment_url=payment_url,
            status=status,
        )
        self.transactions.append(tx)
        return tx


class FakeTrackPointsDAO(TrackPointsDAO):
    def __init__(self) -> None:
        super().__init__(NO_SESSION)
        self.points: dict[int, list[tuple[float, float]]] = {}

    async def list_for_ride(self, ride_id: int) -> list[tuple[float, float]]:
        return self.points.get(ride_id, [])

    async def add_point(self, ride_id: int, seq: int, lat: float, lon: float) -> None:
        self.points.setdefault(ride_id, []).append((lat, lon))

    async def count_for_ride(self, ride_id: int) -> int:
        return len(self.points.get(ride_id, []))


class FakeBotService(BotService):
    def __init__(self) -> None:
        self.notifications: list[dict[str, Any]] = []
        self.admin_logs: list[str] = []

    async def notify_user(self, user_id: int, text: str, reply_markup: Any = None) -> None:
        self.notifications.append({"user_id": user_id, "text": text})

    async def notify_user_now(self, user_id: int, text: str, reply_markup: Any = None) -> bool:
        self.notifications.append({"user_id": user_id, "text": text})
        return True

    async def send_log_to_admin(self, text: str, reply_markup: Any = None) -> None:
        self.admin_logs.append(text)

    def texts_for(self, user_id: int) -> list[str]:
        return [n["text"] for n in self.notifications if n["user_id"] == user_id]


class FakeCache(RedisService):
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    async def get[T: CacheValue](self, key: CacheKey[T], **kwargs: Any) -> T | None:
        return self.store.get(key.build(**kwargs))

    async def set[T: CacheValue](self, key: CacheKey[T], value: T, **kwargs: Any) -> None:
        self.store[key.build(**kwargs)] = value

    async def delete[T: CacheValue](self, key: CacheKey[T], **kwargs: Any) -> None:
        self.store.pop(key.build(**kwargs), None)

    async def exists(self, key: CacheKey[Any], **kwargs: Any) -> bool:
        return key.build(**kwargs) in self.store
