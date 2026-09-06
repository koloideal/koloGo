from collections.abc import Callable
from typing import Any

type CacheValue = bool | str | int | float | dict[str, Any]


class CacheKey[CacheValueT: CacheValue]:
    __slots__ = ("_decode", "_encode", "pattern", "ttl")

    def __init__(
        self,
        pattern: str,
        ttl: int,
        encode: Callable[[CacheValueT], str],
        decode: Callable[[str], CacheValueT],
    ) -> None:
        self.pattern: str = pattern
        self.ttl: int = ttl
        self._encode: Callable[[CacheValueT], str] = encode
        self._decode: Callable[[str], CacheValueT] = decode

    def build(self, **kwargs: Any) -> str:
        return self.pattern.format(**kwargs) if kwargs else self.pattern

    def encode(self, value: CacheValueT) -> str:
        return self._encode(value)

    def decode(self, raw: str) -> CacheValueT:
        return self._decode(raw)


def bool_key(pattern: str, ttl: int) -> CacheKey[bool]:
    return CacheKey(pattern, ttl, lambda v: "1" if v else "0", lambda v: v == "1")


class CacheKeys:
    __slots__ = ("user_banned", "user_vip")

    def __init__(self) -> None:
        self.user_banned: CacheKey[bool] = bool_key("seatbot:user:{user_id}:banned", 300)
        self.user_vip: CacheKey[bool] = bool_key("seatbot:user:{user_id}:vip", 300)
