from seatbot.domain.schemas import User
from seatbot.infrastructure.cache import CacheKeys, RedisService
from seatbot.infrastructure.database.dao import UsersDAO


class UserService:
    def __init__(self, cache: RedisService, cache_keys: CacheKeys, users_dao: UsersDAO) -> None:
        self._cache = cache
        self._cache_keys = cache_keys
        self._users_dao = users_dao

    async def is_banned(self, user_id: int) -> bool:
        cached = await self._cache.get(self._cache_keys.user_banned, user_id=user_id)
        if cached is not None:
            return cached
        user = await self._users_dao.get_by_id(user_id=user_id)
        is_banned = user.is_banned if user else False
        await self._cache.set(self._cache_keys.user_banned, value=is_banned, user_id=user_id)
        return is_banned

    async def is_vip(self, user_id: int) -> bool:
        cached = await self._cache.get(self._cache_keys.user_vip, user_id=user_id)
        if cached is not None:
            return cached
        user = await self._users_dao.get_by_id(user_id=user_id)
        is_vip = user.is_vip if user else False
        await self._cache.set(self._cache_keys.user_vip, value=is_vip, user_id=user_id)
        return is_vip

    async def set_banned(self, user_id: int) -> User | None:
        user = await self._users_dao.ban_user(user_id)
        await self._cache.delete(self._cache_keys.user_banned, user_id=user_id)
        return user

    async def set_unbanned(self, user_id: int) -> User | None:
        user = await self._users_dao.unban_user(user_id)
        await self._cache.delete(self._cache_keys.user_banned, user_id=user_id)
        return user

    async def set_vip(self, user_id: int, is_vip: bool) -> User | None:
        user = await self._users_dao.set_vip(user_id, is_vip)
        await self._cache.delete(self._cache_keys.user_vip, user_id=user_id)
        return user
