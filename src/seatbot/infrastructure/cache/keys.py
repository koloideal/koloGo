from collections.abc import Callable
from typing import Any

import orjson

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


def float_key(pattern: str, ttl: int) -> CacheKey[float]:
    return CacheKey(pattern, ttl, repr, float)


def json_key(pattern: str, ttl: int) -> CacheKey[dict[str, Any]]:
    return CacheKey(
        pattern,
        ttl,
        lambda v: orjson.dumps(v).decode(),
        lambda v: dict(orjson.loads(v)),
    )


class CacheKeys:
    __slots__ = (
        "bookings_pending",
        "locations_all",
        "rate_byn_stars",
        "rate_byn_usd",
        "ride_in_progress",
        "ride_stats",
        "ride_templates",
        "rides_active",
        "rides_upcoming",
        "user_banned",
        "user_booking_counts",
        "user_next_booking",
        "user_vip",
        "users_stats",
        "vip_price",
    )

    def __init__(self) -> None:
        self.user_banned: CacheKey[bool] = bool_key("seatbot:user:{user_id}:banned", 300)
        self.user_vip: CacheKey[bool] = bool_key("seatbot:user:{user_id}:vip", 300)
        self.user_next_booking: CacheKey[dict[str, Any]] = json_key("seatbot:user:{user_id}:next_booking", 90)
        self.user_booking_counts: CacheKey[dict[str, Any]] = json_key(
            "seatbot:user:{user_id}:booking_counts", 300
        )
        self.rides_upcoming: CacheKey[dict[str, Any]] = json_key("seatbot:rides:upcoming", 60)
        self.rides_active: CacheKey[dict[str, Any]] = json_key("seatbot:rides:active", 45)
        self.ride_in_progress: CacheKey[dict[str, Any]] = json_key("seatbot:rides:in_progress", 45)
        self.ride_stats: CacheKey[dict[str, Any]] = json_key("seatbot:ride:{ride_id}:stats", 60)
        self.ride_templates: CacheKey[dict[str, Any]] = json_key("seatbot:rides:templates", 120)
        self.bookings_pending: CacheKey[dict[str, Any]] = json_key("seatbot:bookings:pending", 45)
        self.locations_all: CacheKey[dict[str, Any]] = json_key("seatbot:locations:all", 600)
        self.users_stats: CacheKey[dict[str, Any]] = json_key("seatbot:stats:users", 120)
        self.vip_price: CacheKey[float] = float_key("seatbot:settings:vip_price", 600)
        self.rate_byn_usd: CacheKey[float] = float_key("seatbot:settings:byn_to_usd", 600)
        self.rate_byn_stars: CacheKey[float] = float_key("seatbot:settings:byn_to_stars", 600)
