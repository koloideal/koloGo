from typing import Any

from redis.asyncio import Redis

from seatbot.infrastructure.post_commit import PostCommit

from .keys import CacheKey, CacheValue


class RedisService:
    __slots__ = ("_post_commit", "_redis")

    def __init__(self, redis: Redis, post_commit: PostCommit | None = None) -> None:
        self._redis = redis
        self._post_commit = post_commit

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
        built = key.build(**kwargs)
        await self._redis.delete(built)
        if self._post_commit is not None:
            # повторно после коммита: между удалением и коммитом кэш мог заполниться старыми данными
            self._post_commit.add(lambda: self._redis.delete(built))

    async def exists(self, key: CacheKey[Any], **kwargs: Any) -> bool:
        return bool(await self._redis.exists(key.build(**kwargs)))
