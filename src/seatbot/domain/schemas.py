from dataclasses import dataclass
from datetime import datetime, timedelta
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
    VIP_PURCHASE = "VIP_PURCHASE"
    CRYPTOBOT_TOPUP = "CRYPTOBOT_TOPUP"
    STARS_TOPUP = "STARS_TOPUP"


class TransactionStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class User:
    user_id: int
    username: str | None
    balance: float
    registration_date: datetime
    is_admin: bool
    is_banned: bool
    is_vip: bool
    first_name: str | None = None
    notify_new_rides: bool = False


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
    remind_minutes: int = 30
    vip_hold_minutes: int = 0

    @property
    def is_free(self) -> bool:
        return self.price <= 0

    def is_vip_hold_active(self, now: datetime) -> bool:
        if self.vip_hold_minutes <= 0:
            return False
        return now < self.created_at + timedelta(minutes=self.vip_hold_minutes)

    def vip_hold_remaining_seconds(self, now: datetime) -> int:
        hold_ends = self.created_at + timedelta(minutes=self.vip_hold_minutes)
        delta = (hold_ends - now).total_seconds()
        return max(0, int(delta))


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
    payment_id: str | None = None
    payment_url: str | None = None
    status: TransactionStatus = TransactionStatus.COMPLETED


@dataclass
class Requisite:
    requisite_id: int
    title: str
    value: str
    created_at: datetime


@dataclass
class RideWithStats:
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
    first_name: str | None = None
    registration_date: datetime | None = None


@dataclass
class OverallStats:
    total_users: int
    total_rides_created: int
    total_completed_rides: int
    active_rides: int
    deposit_revenue: float = 0.0
    fact_revenue: float = 0.0
    total_revenue: float = 0.0
