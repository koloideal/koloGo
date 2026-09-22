from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from seatbot.domain.schemas import Location
from seatbot.infrastructure.database.models import Location as OrmLocation


class LocationsDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, name: str, lat: float, lon: float) -> Location:
        orm = OrmLocation(name=name, lat=lat, lon=lon)
        self.session.add(orm)
        await self.session.flush()
        return self._map_to_domain(orm)

    async def get_by_id(self, location_id: int) -> Location | None:
        result = await self.session.execute(
            select(OrmLocation).where(OrmLocation.id == location_id)
        )
        orm = result.scalar_one_or_none()
        return self._map_to_domain(orm) if orm else None

    async def list_all(self, limit: int = 100) -> list[Location]:
        result = await self.session.execute(
            select(OrmLocation).order_by(OrmLocation.name.asc()).limit(limit)
        )
        return [self._map_to_domain(r) for r in result.scalars().all()]

    async def delete(self, location_id: int) -> None:
        await self.session.execute(
            delete(OrmLocation).where(OrmLocation.id == location_id)
        )

    @staticmethod
    def _map_to_domain(orm: OrmLocation) -> Location:
        return Location(
            location_id=orm.id,
            name=orm.name,
            lat=orm.lat,
            lon=orm.lon,
            created_at=orm.created_at,
        )
