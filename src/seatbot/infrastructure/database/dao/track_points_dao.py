from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from seatbot.infrastructure.database.models import RideTrackPoint


class TrackPointsDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_point(self, ride_id: int, seq: int, lat: float, lon: float) -> None:
        self.session.add(RideTrackPoint(ride_id=ride_id, seq=seq, lat=lat, lon=lon))
        await self.session.flush()

    async def count_for_ride(self, ride_id: int) -> int:
        result = await self.session.execute(
            select(func.count(RideTrackPoint.id)).where(RideTrackPoint.ride_id == ride_id)
        )
        return int(result.scalar_one() or 0)

    async def last_point(self, ride_id: int) -> tuple[float, float, datetime] | None:
        result = await self.session.execute(
            select(RideTrackPoint.lat, RideTrackPoint.lon, RideTrackPoint.recorded_at)
            .where(RideTrackPoint.ride_id == ride_id)
            .order_by(RideTrackPoint.seq.desc())
            .limit(1)
        )
        row = result.first()
        return (row.lat, row.lon, row.recorded_at) if row else None

    async def list_for_ride(self, ride_id: int) -> list[tuple[float, float]]:
        result = await self.session.execute(
            select(RideTrackPoint.lat, RideTrackPoint.lon)
            .where(RideTrackPoint.ride_id == ride_id)
            .order_by(RideTrackPoint.seq.asc())
        )
        return [(r.lat, r.lon) for r in result.all()]
