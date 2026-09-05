from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class RideStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class BookingStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"


class TransactionType(str, Enum):
    ADMIN_TOPUP = "ADMIN_TOPUP"
    ADMIN_DECREASE = "ADMIN_DECREASE"
    RIDE_PAYMENT = "RIDE_PAYMENT"
    REFUND = "REFUND"


@dataclass
class User:
    user_id: int
    username: str | None
    balance: float
    registration_date: datetime
    is_admin: bool
    is_banned: bool
    is_vip: bool


@dataclass
class Ride:
    ride_id: int
    departure_at: datetime
    price: float
    seats_total: int
    is_visible: bool
    auto_approve: bool
    status: RideStatus
    created_at: datetime
    note: str | None = None

    @property
    def is_free(self) -> bool:
        return self.price <= 0


@dataclass
class Booking:
    booking_id: int
    ride_id: int
    user_id: int
    status: BookingStatus
    paid_amount: float
    created_at: datetime


@dataclass
class Transaction:
    transaction_id: int
    user_id: int
    amount: float
    type: TransactionType
    ride_id: int | None
    created_at: datetime


@dataclass
class RideWithStats:
    """Ride + агрегированная информация для отображения."""
    ride: Ride
    booked_seats: int
    approved_seats: int
    pending_seats: int

    @property
    def free_seats(self) -> int:
        return self.ride.seats_total - self.approved_seats - self.pending_seats


@dataclass
class UserStats:
    user_id: int
    username: str | None
    total_rides: int
    total_spent: float
    balance: float
    is_vip: bool
    is_banned: bool
    last_ride_at: datetime | None


@dataclass
class OverallStats:
    total_users: int
    total_rides_created: int
    total_completed_rides: int
    total_revenue: float
    active_rides: int
