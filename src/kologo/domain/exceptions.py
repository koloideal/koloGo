from datetime import datetime


class koloGoError(Exception):
    pass


class InsufficientBalanceError(koloGoError):
    def __init__(self, required: float, available: float) -> None:
        super().__init__(f"Insufficient balance: required {required}, available {available}")
        self.required = required
        self.available = available


class NoFreeSeatsError(koloGoError):
    def __init__(self, ride_id: int) -> None:
        super().__init__(f"No free seats for ride {ride_id}")
        self.ride_id = ride_id


class UserBannedError(koloGoError):
    def __init__(self, user_id: int) -> None:
        super().__init__(f"User {user_id} is banned")
        self.user_id = user_id


class RideNotBookableError(koloGoError):
    def __init__(self, ride_id: int, reason: str) -> None:
        super().__init__(f"Ride {ride_id} not bookable: {reason}")
        self.ride_id = ride_id
        self.reason = reason


class AlreadyBookedError(koloGoError):
    def __init__(self, ride_id: int, user_id: int) -> None:
        super().__init__(f"User {user_id} already booked ride {ride_id}")
        self.ride_id = ride_id
        self.user_id = user_id


class RideInPastError(koloGoError):
    def __init__(self, departure_at: datetime) -> None:
        super().__init__(f"Ride departure {departure_at.isoformat()} is in the past")
        self.departure_at = departure_at


class VipHoldActiveError(koloGoError):
    def __init__(self, ride_id: int, remaining_seconds: int) -> None:
        super().__init__(f"Ride {ride_id} vip hold active, {remaining_seconds}s remaining")
        self.ride_id = ride_id
        self.remaining_seconds = remaining_seconds
