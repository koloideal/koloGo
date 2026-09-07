from datetime import UTC, datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from seatbot.domain.schemas import Ride, RideStatus, RideWithStats
from seatbot.infrastructure.database.models import Booking
from seatbot.infrastructure.database.models import Ride as OrmRide


class RidesDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        departure_at: datetime,
        price: float,
        seats_total: int,
        auto_approve: bool,
        note: str | None = None,
        is_visible: bool = True,
        remind_minutes: int = 30,
    ) -> Ride:
        orm_ride = OrmRide(
            departure_at=departure_at,
            price=price,
            seats_total=seats_total,
            auto_approve=auto_approve,
            is_visible=is_visible,
            status=RideStatus.OPEN.value,
            note=note,
            remind_minutes=remind_minutes,
        )
        self.session.add(orm_ride)
        await self.session.flush()
        return self._map_to_domain(orm_ride)

    async def get_by_id(self, ride_id: int) -> Ride | None:
        result = await self.session.execute(select(OrmRide).where(OrmRide.id == ride_id))
        orm_ride = result.scalar_one_or_none()
        return self._map_to_domain(orm_ride) if orm_ride else None

    async def get_by_id_for_update(self, ride_id: int) -> Ride | None:
        result = await self.session.execute(
            select(OrmRide).where(OrmRide.id == ride_id).with_for_update()
        )
        orm_ride = result.scalar_one_or_none()
        return self._map_to_domain(orm_ride) if orm_ride else None

    async def get_with_stats(self, ride_id: int) -> RideWithStats | None:
        ride = await self.get_by_id(ride_id)
        if not ride:
            return None

        approved = await self._count_status(ride_id, {"approved"})
        pending = await self._count_status(ride_id, {"pending"})
        booked = approved + pending
        return RideWithStats(
            ride=ride,
            booked_seats=booked,
            approved_seats=approved,
            pending_seats=pending,
        )

    async def list_upcoming_visible(self, now: datetime | None = None) -> list[RideWithStats]:
        now = now or datetime.now(UTC)
        query = (
            select(OrmRide)
            .where(
                OrmRide.is_visible.is_(True),
                OrmRide.departure_at > now,
                OrmRide.status == RideStatus.OPEN.value,
            )
            .order_by(OrmRide.departure_at.asc())
        )
        result = await self.session.execute(query)
        rides = [self._map_to_domain(r) for r in result.scalars().all()]
        out: list[RideWithStats] = []
        for ride in rides:
            approved = await self._count_status(ride.ride_id, {"approved"})
            pending = await self._count_status(ride.ride_id, {"pending"})
            out.append(
                RideWithStats(
                    ride=ride,
                    booked_seats=approved + pending,
                    approved_seats=approved,
                    pending_seats=pending,
                )
            )
        return out

    async def list_all(self, limit: int = 50) -> list[RideWithStats]:
        status_order = case(
            (OrmRide.status == RideStatus.OPEN.value, 0),
            (OrmRide.status == RideStatus.CLOSED.value, 1),
            (OrmRide.status == RideStatus.COMPLETED.value, 2),
            (OrmRide.status == RideStatus.CANCELLED.value, 3),
            else_=4,
        )
        query = select(OrmRide).order_by(status_order, OrmRide.departure_at.asc()).limit(limit)
        result = await self.session.execute(query)
        rides = [self._map_to_domain(r) for r in result.scalars().all()]
        out: list[RideWithStats] = []
        for ride in rides:
            approved = await self._count_status(ride.ride_id, {"approved"})
            pending = await self._count_status(ride.ride_id, {"pending"})
            out.append(
                RideWithStats(
                    ride=ride,
                    booked_seats=approved + pending,
                    approved_seats=approved,
                    pending_seats=pending,
                )
            )
        return out

    async def list_active(self) -> list[Ride]:
        query = (
            select(OrmRide)
            .where(OrmRide.status.in_([RideStatus.OPEN.value, RideStatus.CLOSED.value]))
            .order_by(OrmRide.departure_at.asc())
        )
        result = await self.session.execute(query)
        return [self._map_to_domain(r) for r in result.scalars().all()]

    async def list_templates(self, limit: int = 10) -> list[Ride]:
        query = select(OrmRide).order_by(OrmRide.departure_at.desc()).limit(limit * 3)
        result = await self.session.execute(query)
        rides = [self._map_to_domain(r) for r in result.scalars().all()]
        seen: set[tuple[float, str | None]] = set()
        unique: list[Ride] = []
        for ride in rides:
            key = (float(ride.price), ride.note)
            if key not in seen:
                seen.add(key)
                unique.append(ride)
            if len(unique) >= limit:
                break
        return unique

    async def set_status(self, ride_id: int, status: RideStatus) -> Ride | None:
        result = await self.session.execute(select(OrmRide).where(OrmRide.id == ride_id))
        orm_ride = result.scalar_one_or_none()
        if not orm_ride:
            return None
        orm_ride.status = status.value
        return self._map_to_domain(orm_ride)

    async def set_visibility(self, ride_id: int, is_visible: bool) -> Ride | None:
        result = await self.session.execute(select(OrmRide).where(OrmRide.id == ride_id))
        orm_ride = result.scalar_one_or_none()
        if not orm_ride:
            return None
        orm_ride.is_visible = is_visible
        return self._map_to_domain(orm_ride)

    async def set_auto_approve(self, ride_id: int, auto_approve: bool) -> Ride | None:
        result = await self.session.execute(select(OrmRide).where(OrmRide.id == ride_id))
        orm_ride = result.scalar_one_or_none()
        if not orm_ride:
            return None
        orm_ride.auto_approve = auto_approve
        return self._map_to_domain(orm_ride)

    async def count_total(self) -> int:
        result = await self.session.execute(select(func.count(OrmRide.id)))
        return int(result.scalar_one() or 0)

    async def is_remind_sent(self, ride_id: int) -> bool:
        result = await self.session.execute(select(OrmRide.remind_sent).where(OrmRide.id == ride_id))
        return bool(result.scalar_one_or_none())

    async def mark_remind_sent(self, ride_id: int) -> None:
        result = await self.session.execute(select(OrmRide).where(OrmRide.id == ride_id))
        orm_ride = result.scalar_one_or_none()
        if orm_ride:
            orm_ride.remind_sent = True
            await self.session.flush()

    async def count_by_status(self, status: RideStatus) -> int:
        result = await self.session.execute(
            select(func.count(OrmRide.id)).where(OrmRide.status == status.value)
        )
        return int(result.scalar_one() or 0)

    async def _count_status(self, ride_id: int, statuses: set[str]) -> int:
        result = await self.session.execute(
            select(func.count(Booking.id)).where(
                Booking.ride_id == ride_id,
                Booking.status.in_(statuses),
            )
        )
        return int(result.scalar_one() or 0)

    @staticmethod
    def _map_to_domain(orm_ride: OrmRide) -> Ride:
        return Ride(
            ride_id=orm_ride.id,
            departure_at=orm_ride.departure_at,
            price=float(orm_ride.price),
            seats_total=orm_ride.seats_total,
            is_visible=orm_ride.is_visible,
            auto_approve=orm_ride.auto_approve,
            status=RideStatus(orm_ride.status),
            created_at=orm_ride.created_at,
            note=orm_ride.note,
            remind_minutes=orm_ride.remind_minutes,
        )
