from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from seatbot.domain.schemas import Booking, BookingStatus
from seatbot.infrastructure.database.models import Booking as OrmBooking
from seatbot.infrastructure.database.models import Ride as OrmRide
from seatbot.infrastructure.database.models import User as OrmUser


class BookingsDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, ride_id: int, user_id: int, paid_amount: float) -> Booking:
        orm_booking = OrmBooking(
            ride_id=ride_id,
            user_id=user_id,
            status=BookingStatus.PENDING.value,
            paid_amount=paid_amount,
        )
        self.session.add(orm_booking)
        await self.session.flush()
        return self._map_to_domain(orm_booking)

    async def get_by_id(self, booking_id: int) -> Booking | None:
        result = await self.session.execute(select(OrmBooking).where(OrmBooking.id == booking_id))
        orm = result.scalar_one_or_none()
        return self._map_to_domain(orm) if orm else None

    async def get_by_id_for_update(self, booking_id: int) -> Booking | None:
        result = await self.session.execute(
            select(OrmBooking).where(OrmBooking.id == booking_id).with_for_update()
        )
        orm = result.scalar_one_or_none()
        return self._map_to_domain(orm) if orm else None

    async def get_by_ride_and_user(
        self, ride_id: int, user_id: int, only_active: bool = True
    ) -> Booking | None:
        query = select(OrmBooking).where(
            OrmBooking.ride_id == ride_id,
            OrmBooking.user_id == user_id,
        )
        if only_active:
            query = query.where(
                OrmBooking.status.in_([BookingStatus.PENDING.value, BookingStatus.APPROVED.value])
            )
        result = await self.session.execute(query)
        orm = result.scalar_one_or_none()
        return self._map_to_domain(orm) if orm else None

    async def list_for_ride(self, ride_id: int, only_active: bool = False) -> list[Booking]:
        query = select(OrmBooking).where(OrmBooking.ride_id == ride_id)
        if only_active:
            query = query.where(
                OrmBooking.status.in_([BookingStatus.PENDING.value, BookingStatus.APPROVED.value])
            )
        query = query.order_by(OrmBooking.created_at.asc())
        result = await self.session.execute(query)
        return [self._map_to_domain(b) for b in result.scalars().all()]

    async def list_for_user(self, user_id: int, limit: int = 50) -> list[Booking]:
        result = await self.session.execute(
            select(OrmBooking)
            .where(OrmBooking.user_id == user_id)
            .order_by(OrmBooking.created_at.desc())
            .limit(limit)
        )
        return [self._map_to_domain(b) for b in result.scalars().all()]

    async def list_for_ride_with_status(self, ride_id: int, statuses: set[BookingStatus]) -> list[Booking]:
        status_values = [s.value for s in statuses]
        result = await self.session.execute(
            select(OrmBooking)
            .where(
                OrmBooking.ride_id == ride_id,
                OrmBooking.status.in_(status_values),
            )
            .order_by(OrmBooking.created_at.asc())
        )
        return [self._map_to_domain(b) for b in result.scalars().all()]

    async def set_status(self, booking_id: int, status: BookingStatus) -> Booking | None:
        result = await self.session.execute(select(OrmBooking).where(OrmBooking.id == booking_id))
        orm = result.scalar_one_or_none()
        if not orm:
            return None
        orm.status = status.value
        return self._map_to_domain(orm)

    async def set_paid_amount(self, booking_id: int, paid_amount: float) -> Booking | None:
        result = await self.session.execute(select(OrmBooking).where(OrmBooking.id == booking_id))
        orm = result.scalar_one_or_none()
        if not orm:
            return None
        orm.paid_amount = Decimal(str(paid_amount))
        return self._map_to_domain(orm)

    async def count_completed_for_user(self, user_id: int) -> int:
        result = await self.session.execute(
            select(func.count(OrmBooking.id)).where(
                OrmBooking.user_id == user_id,
                OrmBooking.status == BookingStatus.COMPLETED.value,
            )
        )
        return int(result.scalar_one() or 0)

    async def sum_paid_for_user(self, user_id: int) -> float:
        result = await self.session.execute(
            select(func.coalesce(func.sum(OrmBooking.paid_amount), 0)).where(
                OrmBooking.user_id == user_id,
                OrmBooking.status == BookingStatus.COMPLETED.value,
            )
        )
        return float(result.scalar_one() or 0)

    async def sum_fact_revenue(self) -> float:
        result = await self.session.execute(
            select(func.coalesce(func.sum(OrmRide.price), 0))
            .select_from(OrmBooking)
            .join(OrmRide, OrmBooking.ride_id == OrmRide.id)
            .join(OrmUser, OrmBooking.user_id == OrmUser.user_id)
            .where(
                OrmBooking.status == BookingStatus.COMPLETED.value,
                OrmBooking.paid_amount == 0,
                OrmRide.price > 0,
                OrmUser.is_vip.is_(False),
            )
        )
        return float(result.scalar_one() or 0)

    async def has_approved_for_user(self, user_id: int) -> bool:
        result = await self.session.execute(
            select(OrmBooking.id)
            .where(
                OrmBooking.user_id == user_id,
                OrmBooking.status == BookingStatus.APPROVED.value,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def count_active_for_ride(self, ride_id: int) -> int:
        result = await self.session.execute(
            select(func.count(OrmBooking.id)).where(
                OrmBooking.ride_id == ride_id,
                OrmBooking.status.in_([BookingStatus.PENDING.value, BookingStatus.APPROVED.value]),
            )
        )
        return int(result.scalar_one() or 0)

    @staticmethod
    def _map_to_domain(orm: OrmBooking) -> Booking:
        return Booking(
            booking_id=orm.id,
            ride_id=orm.ride_id,
            user_id=orm.user_id,
            status=BookingStatus(orm.status),
            paid_amount=float(orm.paid_amount),
            created_at=orm.created_at,
        )
