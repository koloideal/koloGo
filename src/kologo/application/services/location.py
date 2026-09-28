from kologo.domain.schemas import Location
from kologo.infrastructure.cache import (CacheKeys, RedisService, dump_location,
                                         load_location)
from kologo.infrastructure.database.dao import LocationsDAO


class LocationService:
    def __init__(self, cache: RedisService, cache_keys: CacheKeys, locations_dao: LocationsDAO) -> None:
        self._cache = cache
        self._cache_keys = cache_keys
        self._locations_dao = locations_dao

    async def get_by_id(self, location_id: int) -> Location | None:
        return await self._locations_dao.get_by_id(location_id)

    async def list_all(self) -> list[Location]:
        cached = await self._cache.get(self._cache_keys.locations_all)
        if cached is not None:
            return [load_location(d) for d in cached["items"]]
        locations = await self._locations_dao.list_all()
        await self._cache.set(
            self._cache_keys.locations_all, {"items": [dump_location(l) for l in locations]}
        )
        return locations

    async def create(self, name: str, lat: float, lon: float) -> Location:
        location = await self._locations_dao.create(name, lat, lon)
        await self._cache.delete(self._cache_keys.locations_all)
        return location

    async def update_geo(self, location_id: int, lat: float, lon: float) -> Location | None:
        location = await self._locations_dao.update_geo(location_id, lat, lon)
        await self._cache.delete(self._cache_keys.locations_all)
        return location

    async def delete(self, location_id: int) -> None:
        await self._locations_dao.delete(location_id)
        await self._cache.delete(self._cache_keys.locations_all)
