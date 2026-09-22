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
        origin: str,
        destination: str,
        note: str | None = None,
        is_visible: bool = True,
        remind_minutes: int = 30,
        vip_hold_minutes: int = 0,
        origin_lat: float | None = None,
        origin_lon: float | None = None,
        destination_lat: float | None = None,
        destination_lon: float | None = None,
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
            vip_hold_minutes=vip_hold_minutes,
            origin=origin,
            destination=destination,
            origin_lat=origin_lat,
            origin_lon=origin_lon,
            destination_lat=destination_lat,
            destination_lon=destination_lon,
        )
        self.session.add(orm_ride)
        await self.session.flush()
        return self._map_to_domain(orm_ride)

    async def get_by_id(self, ride_id: int) -> Ride | None:
        result = await self.session.execute(select(OrmRide).where(OrmRide.id == ride_id))
        orm_ride = result.scalar_one_or_none()
        return self._map_to_domain(orm_ride) if orm_ride else None

    async def get_by_id_for_update(self, ride_id: int) -> Ride | None:
        result = await self.session.execute(select(OrmRide).where(OrmRide.id == ride_id).with_for_update())
        orm_ride = result.scalar_one_or_none()
        return self._map_to_domain(orm_ride) if orm_ride else None

    async def get_with_stats(self, ride_id: int) -> RideWithStats | None:
        ride = await self.get_by_id(ride_id)
        if not ride:
            return None
        return await self._with_stats(ride)

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
        return [await self._with_stats(ride) for ride in rides]

    async def list_all(self, limit: int = 50) -> list[RideWithStats]:
        status_order = case(
            (OrmRide.status == RideStatus.OPEN.value, 0),
            (OrmRide.status == RideStatus.IN_PROGRESS.value, 1),
            (OrmRide.status == RideStatus.CLOSED.value, 2),
            (OrmRide.status == RideStatus.COMPLETED.value, 3),
            (OrmRide.status == RideStatus.CANCELLED.value, 4),
            else_=5,
        )
        done_ts = func.extract("epoch", func.coalesce(OrmRide.finished_at, OrmRide.departure_at))
        dep_ts = func.extract("epoch", OrmRide.departure_at)
        recency = case(
            (
                OrmRide.status.in_([RideStatus.COMPLETED.value, RideStatus.CANCELLED.value]),
                -done_ts,
            ),
            else_=dep_ts,
        )
        query = select(OrmRide).order_by(status_order, recency).limit(limit)
        result = await self.session.execute(query)
        rides = [self._map_to_domain(r) for r in result.scalars().all()]
        return [await self._with_stats(ride) for ride in rides]

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
        seen: set[tuple[float, str | None, str, str]] = set()
        unique: list[Ride] = []
        for ride in rides:
            key = (float(ride.price), ride.note, ride.origin, ride.destination)
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

    async def set_departure_at(self, ride_id: int, departure_at: datetime) -> Ride | None:
        result = await self.session.execute(select(OrmRide).where(OrmRide.id == ride_id))
        orm_ride = result.scalar_one_or_none()
        if not orm_ride:
            return None
        orm_ride.departure_at = departure_at
        orm_ride.remind_sent = False
        await self.session.flush()
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

    async def set_finished_at(self, ride_id: int, finished_at: datetime) -> None:
        result = await self.session.execute(select(OrmRide).where(OrmRide.id == ride_id))
        orm_ride = result.scalar_one_or_none()
        if orm_ride:
            orm_ride.finished_at = finished_at
            orm_ride.live_chat_id = None
            orm_ride.live_message_id = None
            await self.session.flush()

    async def set_awaiting_live(self, ride_id: int, value: bool) -> None:
        result = await self.session.execute(select(OrmRide).where(OrmRide.id == ride_id))
        orm_ride = result.scalar_one_or_none()
        if orm_ride:
            orm_ride.awaiting_live_geo = value
            await self.session.flush()

    async def get_awaiting_live_orm(self) -> OrmRide | None:
        result = await self.session.execute(
            select(OrmRide)
            .where(
                OrmRide.awaiting_live_geo.is_(True),
                OrmRide.status.in_([RideStatus.OPEN.value, RideStatus.CLOSED.value]),
            )
            .order_by(OrmRide.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_tracking_orm(self, chat_id: int, message_id: int) -> OrmRide | None:
        result = await self.session.execute(
            select(OrmRide).where(
                OrmRide.status == RideStatus.IN_PROGRESS.value,
                OrmRide.live_chat_id == chat_id,
                OrmRide.live_message_id == message_id,
            )
        )
        return result.scalar_one_or_none()

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

    async def _with_stats(self, ride: Ride) -> RideWithStats:
        approved = await self._count_status(ride.ride_id, {"approved"})
        pending = await self._count_status(ride.ride_id, {"pending"})
        finished = await self._count_status(ride.ride_id, {"completed", "no_show"})
        return RideWithStats(
            ride=ride,
            booked_seats=approved + pending,
            approved_seats=approved,
            pending_seats=pending,
            finished_seats=finished,
        )

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
            vip_hold_minutes=orm_ride.vip_hold_minutes,
            origin=orm_ride.origin,
            destination=orm_ride.destination,
            origin_lat=orm_ride.origin_lat,
            origin_lon=orm_ride.origin_lon,
            destination_lat=orm_ride.destination_lat,
            destination_lon=orm_ride.destination_lon,
            started_at=orm_ride.started_at,
            finished_at=orm_ride.finished_at,
            track_distance_m=orm_ride.track_distance_m,
            track_max_speed_mps=orm_ride.track_max_speed_mps,
        )
