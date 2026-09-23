import math
from collections.abc import Sequence

from seatbot.infrastructure.config.models import GeoConfig

EARTH_RADIUS_M = 6_371_000


class GeoService:
    def __init__(self, config: GeoConfig) -> None:
        self._config = config

    @staticmethod
    def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))

    @staticmethod
    def segment_distance_m(a: tuple[float, float], b: tuple[float, float], p: tuple[float, float]) -> float:
        k = math.cos(math.radians(p[0]))

        def project(pt: tuple[float, float]) -> tuple[float, float]:
            return (
                math.radians(pt[1] - p[1]) * k * EARTH_RADIUS_M,
                math.radians(pt[0] - p[0]) * EARTH_RADIUS_M,
            )

        (ax, ay), (bx, by) = project(a), project(b)
        dx, dy = bx - ax, by - ay
        length_sq = dx * dx + dy * dy
        t = 0.0 if length_sq == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / length_sq))
        return math.hypot(ax + t * dx, ay + t * dy)

    def downsample_track(
        self, points: Sequence[tuple[float, float]], max_points: int | None = None
    ) -> list[tuple[float, float]]:
        limit = max_points if max_points is not None else self._config.yandex_max_route_points
        if len(points) <= limit:
            return list(points)
        step = (len(points) - 1) / (limit - 1)
        return [points[round(i * step)] for i in range(limit - 1)] + [points[-1]]

    def yandex_route_url(self, points: Sequence[tuple[float, float]]) -> str:
        pts = self.downsample_track(points)
        rtext = "~".join(f"{lat},{lon}" for lat, lon in pts)
        return f"https://yandex.com/maps/?rtext={rtext}&rtt=auto"
