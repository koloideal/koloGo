import io
import math
from collections.abc import Sequence

EARTH_RADIUS_M = 6_371_000


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def downsample_track(points: Sequence[tuple[float, float]], max_points: int = 40) -> list[tuple[float, float]]:
    if len(points) <= max_points:
        return list(points)
    step = (len(points) - 1) / (max_points - 1)
    return [points[round(i * step)] for i in range(max_points - 1)] + [points[-1]]


def yandex_route_url(points: Sequence[tuple[float, float]]) -> str:
    pts = downsample_track(points)
    rtext = "~".join(f"{lat},{lon}" for lat, lon in pts)
    return f"https://yandex.com/maps/?rtext={rtext}&rtt=auto"


def render_track_png(points: Sequence[tuple[float, float]], size: int = 800) -> bytes:
    from PIL import Image, ImageDraw

    margin = 40
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)
    cos_lat = math.cos(math.radians((min_lat + max_lat) / 2)) or 1e-9

    span_x = max((max_lon - min_lon) * cos_lat, 1e-9)
    span_y = max(max_lat - min_lat, 1e-9)
    inner = size - 2 * margin
    scale = inner / max(span_x, span_y)

    def to_xy(lat: float, lon: float) -> tuple[float, float]:
        x = margin + (lon - min_lon) * cos_lat * scale + (inner - span_x * scale) / 2
        y = margin + (max_lat - lat) * scale + (inner - span_y * scale) / 2
        return x, y

    img = Image.new("RGB", (size, size), (245, 246, 248))
    draw = ImageDraw.Draw(img)

    xy = [to_xy(lat, lon) for lat, lon in points]
    if len(xy) >= 2:
        draw.line(xy, fill=(37, 99, 235), width=5, joint="curve")

    def pin(x: float, y: float, color: tuple[int, int, int]) -> None:
        r = 10
        draw.ellipse((x - r, y - r, x + r, y + r), fill=color, outline=(255, 255, 255), width=3)

    pin(*xy[0], (34, 139, 34))
    pin(*xy[-1], (200, 30, 30))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
