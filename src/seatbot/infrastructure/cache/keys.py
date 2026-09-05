from collections.abc import Callable
from typing import Any, Generic, TypeVar

import orjson

CacheValue = TypeVar("CacheValue", bool, str, int, float, "dict[str, Any]")


class CacheKey(Generic[CacheValue]):  # noqa: UP046 — намеренно используем Generic из typing
    __slots__ = ("_decode", "_encode", "pattern", "ttl")

    def __init__(
        self,
        pattern: str,
        ttl: int,
        encode: Callable[[CacheValue], str],
        decode: Callable[[str], CacheValue],
    ) -> None:
        self.pattern: str = pattern
        self.ttl: int = ttl
        self._encode: Callable[[CacheValue], str] = encode
        self._decode: Callable[[str], CacheValue] = decode

    def build(self, **kwargs: Any) -> str:
        return self.pattern.format(**kwargs) if kwargs else self.pattern

    def encode(self, value: CacheValue) -> str:
        return self._encode(value)

    def decode(self, raw: str) -> CacheValue:
        return self._decode(raw)


def bool_key(pattern: str, ttl: int) -> CacheKey[bool]:
    return CacheKey(pattern, ttl, lambda v: "1" if v else "0", lambda v: v == "1")


def str_key(pattern: str, ttl: int) -> CacheKey[str]:
    return CacheKey(pattern, ttl, lambda v: v, lambda v: v)


def int_key(pattern: str, ttl: int) -> CacheKey[int]:
    return CacheKey(pattern, ttl, str, int)


def json_key(pattern: str, ttl: int) -> CacheKey[dict[str, Any]]:
    return CacheKey(pattern, ttl, lambda value: orjson.dumps(value).decode(), orjson.loads)


class CacheKeys:
    """Типобезопасный реестр кэш-ключей. Не dataclass — значения вычисляются в __init__."""

    __slots__ = ("user_banned", "user_locale", "user_vip")

    def __init__(self) -> None:
        self.user_banned: CacheKey[bool] = bool_key("seatbot:user:{user_id}:banned", 300)
        self.user_vip: CacheKey[bool] = bool_key("seatbot:user:{user_id}:vip", 300)
