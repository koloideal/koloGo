from dataclasses import asdict
from datetime import datetime
from typing import Any

from kologo.domain.schemas import (Booking, BookingStatus, Location, Ride, RideStatus,
                                   RideWithStats, UserStats)


def _dt(value: Any) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


def _opt_dt(value: Any) -> datetime | None:
    return _dt(value) if value else None


def dump_ride(ride: Ride) -> dict[str, Any]:
    return asdict(ride)


def load_ride(data: dict[str, Any]) -> Ride:
    return Ride(
        ride_id=data["ride_id"],
        departure_at=_dt(data["departure_at"]),
        price=float(data["price"]),
        seats_total=data["seats_total"],
        is_visible=data["is_visible"],
        auto_approve=data["auto_approve"],
        status=RideStatus(data["status"]),
        created_at=_dt(data["created_at"]),
        origin=data["origin"],
        destination=data["destination"],
        note=data.get("note"),
        remind_minutes=data.get("remind_minutes", 30),
        vip_hold_minutes=data.get("vip_hold_minutes", 0),
        origin_lat=data.get("origin_lat"),
        origin_lon=data.get("origin_lon"),
        destination_lat=data.get("destination_lat"),
        destination_lon=data.get("destination_lon"),
        started_at=_opt_dt(data.get("started_at")),
        finished_at=_opt_dt(data.get("finished_at")),
        track_distance_m=data.get("track_distance_m", 0.0),
        track_max_speed_mps=data.get("track_max_speed_mps", 0.0),
    )


def dump_ride_stats(rws: RideWithStats) -> dict[str, Any]:
    return {
        "ride": dump_ride(rws.ride),
        "booked_seats": rws.booked_seats,
        "approved_seats": rws.approved_seats,
        "pending_seats": rws.pending_seats,
        "finished_seats": rws.finished_seats,
    }


def load_ride_stats(data: dict[str, Any]) -> RideWithStats:
    return RideWithStats(
        ride=load_ride(data["ride"]),
        booked_seats=data["booked_seats"],
        approved_seats=data["approved_seats"],
        pending_seats=data["pending_seats"],
        finished_seats=data.get("finished_seats", 0),
    )


def dump_booking(booking: Booking) -> dict[str, Any]:
    return asdict(booking)


def load_booking(data: dict[str, Any]) -> Booking:
    return Booking(
        booking_id=data["booking_id"],
        ride_id=data["ride_id"],
        user_id=data["user_id"],
        status=BookingStatus(data["status"]),
        paid_amount=float(data["paid_amount"]),
        created_at=_dt(data["created_at"]),
    )


def dump_location(location: Location) -> dict[str, Any]:
    return asdict(location)


def load_location(data: dict[str, Any]) -> Location:
    return Location(
        location_id=data["location_id"],
        name=data["name"],
        lat=float(data["lat"]),
        lon=float(data["lon"]),
        created_at=_dt(data["created_at"]),
    )


def dump_user_stats(stats: UserStats) -> dict[str, Any]:
    return asdict(stats)


def load_user_stats(data: dict[str, Any]) -> UserStats:
    return UserStats(
        user_id=data["user_id"],
        username=data.get("username"),
        total_rides=data["total_rides"],
        total_spent=float(data["total_spent"]),
        balance=float(data["balance"]),
        is_vip=data["is_vip"],
        is_banned=data["is_banned"],
        last_ride_at=_opt_dt(data.get("last_ride_at")),
        first_name=data.get("first_name"),
        registration_date=_opt_dt(data.get("registration_date")),
        top_route=data.get("top_route"),
    )
