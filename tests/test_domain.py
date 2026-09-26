from datetime import UTC, datetime

from seatbot.domain.schemas import RideGeoStats, RideStatus, RideWithStats
from tests.factories import make_ride


def test_is_free_when_price_zero() -> None:
    assert make_ride(price=0).is_free


def test_is_free_when_price_negative() -> None:
    assert make_ride(price=-1).is_free


def test_not_free_when_price_positive() -> None:
    assert not make_ride(price=10).is_free


def test_vip_hold_active_within_window() -> None:
    ride = make_ride(vip_hold_minutes=15, created_ago_minutes=10)
    assert ride.is_vip_hold_active(datetime.now(UTC))


def test_vip_hold_inactive_after_window() -> None:
    ride = make_ride(vip_hold_minutes=15, created_ago_minutes=20)
    assert not ride.is_vip_hold_active(datetime.now(UTC))


def test_vip_hold_inactive_when_zero() -> None:
    assert not make_ride(vip_hold_minutes=0).is_vip_hold_active(datetime.now(UTC))


def test_vip_hold_remaining_seconds() -> None:
    ride = make_ride(vip_hold_minutes=15, created_ago_minutes=10)
    remaining = ride.vip_hold_remaining_seconds(datetime.now(UTC))
    assert 290 <= remaining <= 300


def test_vip_hold_remaining_seconds_floor_at_zero() -> None:
    ride = make_ride(vip_hold_minutes=15, created_ago_minutes=20)
    assert ride.vip_hold_remaining_seconds(datetime.now(UTC)) == 0


def test_ride_with_stats_free_seats() -> None:
    rws = RideWithStats(ride=make_ride(seats_total=4), booked_seats=3, approved_seats=3, pending_seats=0)
    assert rws.free_seats == 1


def test_ride_with_stats_free_seats_never_negative() -> None:
    rws = RideWithStats(ride=make_ride(seats_total=4), booked_seats=10, approved_seats=6, pending_seats=4)
    assert rws.free_seats == 0


def test_geo_stats_avg_speed_zero_when_no_duration() -> None:
    stats = RideGeoStats(total_distance_m=10_000, total_duration_s=0)
    assert stats.avg_speed_kmh == 0.0


def test_geo_stats_avg_speed() -> None:
    stats = RideGeoStats(total_distance_m=36_000, total_duration_s=3600)
    assert stats.avg_speed_kmh == 36.0


def test_geo_stats_avgs_guard_zero_rides() -> None:
    stats = RideGeoStats()
    assert stats.avg_distance_m == 0.0
    assert stats.avg_duration_s == 0.0


def test_ride_status_values() -> None:
    assert {s.value for s in RideStatus} == {"open", "closed", "in_progress", "completed", "cancelled"}
