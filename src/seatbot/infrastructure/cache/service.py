from typing import Any

from redis.asyncio import Redis

from .keys import CacheKey, CacheValue


class RedisService:
    __slots__ = ("_redis",)

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get[T: CacheValue](self, key: CacheKey[T], **kwargs: Any) -> T | None:
        raw = await self._redis.get(key.build(**kwargs))
        if raw is None:
            return None
        return key.decode(str(raw))

    async def set[T: CacheValue](self, key: CacheKey[T], value: T, **kwargs: Any) -> None:
        built = key.build(**kwargs)
        encoded = key.encode(value)
        if key.ttl > 0:
            await self._redis.setex(built, key.ttl, encoded)
        else:
            await self._redis.set(built, encoded)

    async def delete[T: CacheValue](self, key: CacheKey[T], **kwargs: Any) -> None:
        await self._redis.delete(key.build(**kwargs))

    async def exists(self, key: CacheKey[Any], **kwargs: Any) -> bool:
        return bool(await self._redis.exists(key.build(**kwargs)))
