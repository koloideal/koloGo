import pytest

from kologo.infrastructure.geo import GeoService


def test_haversine_same_point_is_zero(geo: GeoService) -> None:
    assert geo.haversine_m(53.9, 27.5, 53.9, 27.5) == 0.0


def test_haversine_one_degree_latitude_is_about_111km(geo: GeoService) -> None:
    assert geo.haversine_m(0.0, 0.0, 1.0, 0.0) == pytest.approx(111_195, rel=0.01)


def test_haversine_quarter_meridian(geo: GeoService) -> None:
    assert geo.haversine_m(0.0, 0.0, 0.0, 90.0) == pytest.approx(10_007_500, rel=0.01)


def test_haversine_is_symmetric(geo: GeoService) -> None:
    assert geo.haversine_m(53.9, 27.5, 53.5, 28.0) == geo.haversine_m(53.5, 28.0, 53.9, 27.5)


def test_downsample_returns_copy_when_within_limit(geo: GeoService) -> None:
    points = [(1.0, 1.0), (2.0, 2.0)]
    result = geo.downsample_track(points)
    assert result == points


def test_downsample_keeps_first_and_last(geo: GeoService) -> None:
    points = [(float(i), float(i)) for i in range(100)]
    result = geo.downsample_track(points, max_points=10)
    assert len(result) == 10
    assert result[0] == points[0]
    assert result[-1] == points[-1]


def test_downsample_uses_config_limit(geo: GeoService) -> None:
    points = [(float(i), 0.0) for i in range(50)]
    assert len(geo.downsample_track(points)) == 20


def test_yandex_route_url_format(geo: GeoService) -> None:
    url = geo.yandex_route_url([(53.9, 27.5), (54.0, 28.0)])
    assert url.startswith("https://yandex.com/maps/?rtext=")
    assert "rtt=auto" in url
    assert "53.9,27.5" in url
    assert "54.0,28.0" in url


def test_yandex_route_url_caps_points_at_config_limit(geo: GeoService) -> None:
    points = [(50.0 + i * 0.001, 20.0) for i in range(100)]
    url = geo.yandex_route_url(points)
    rtext = url.split("rtext=")[1].split("&")[0]
    assert len(rtext.split("~")) == 20
