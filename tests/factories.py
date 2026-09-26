from datetime import UTC, datetime, timedelta

from seatbot.domain.schemas import Booking, BookingStatus, Ride, RideStatus, User


def make_ride(
    *,
    ride_id: int = 1,
    departure_in_minutes: float = 60,
    price: float = 10.0,
    seats_total: int = 4,
    status: RideStatus = RideStatus.OPEN,
    is_visible: bool = True,
    auto_approve: bool = False,
    vip_hold_minutes: int = 0,
    created_ago_minutes: float = 0,
    started_ago_minutes: float | None = None,
    finished_ago_minutes: float | None = None,
    track_distance_m: float = 0.0,
    track_max_speed_mps: float = 0.0,
    origin: str = "Новое Поле",
    destination: str = "Минск",
) -> Ride:
    now = datetime.now(UTC)
    return Ride(
        ride_id=ride_id,
        departure_at=now + timedelta(minutes=departure_in_minutes),
        price=price,
        seats_total=seats_total,
        is_visible=is_visible,
        auto_approve=auto_approve,
        status=status,
        created_at=now - timedelta(minutes=created_ago_minutes),
        origin=origin,
        destination=destination,
        vip_hold_minutes=vip_hold_minutes,
        started_at=(now - timedelta(minutes=started_ago_minutes)) if started_ago_minutes is not None else None,
        finished_at=(now - timedelta(minutes=finished_ago_minutes)) if finished_ago_minutes is not None else None,
        track_distance_m=track_distance_m,
        track_max_speed_mps=track_max_speed_mps,
    )


def make_user(
    user_id: int = 1,
    *,
    balance: float = 100.0,
    is_vip: bool = False,
    is_banned: bool = False,
    is_admin: bool = False,
    username: str | None = "passenger",
) -> User:
    return User(
        user_id=user_id,
        username=username,
        balance=balance,
        registration_date=datetime.now(UTC) - timedelta(days=30),
        is_admin=is_admin,
        is_banned=is_banned,
        is_vip=is_vip,
    )


def make_booking(
    booking_id: int = 1,
    *,
    ride_id: int = 1,
    user_id: int = 1,
    status: BookingStatus = BookingStatus.PENDING,
    paid_amount: float = 0.0,
) -> Booking:
    return Booking(
        booking_id=booking_id,
        ride_id=ride_id,
        user_id=user_id,
        status=status,
        paid_amount=paid_amount,
        created_at=datetime.now(UTC),
    )
