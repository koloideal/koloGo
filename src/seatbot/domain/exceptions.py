class SeatBotError(Exception):
    """Базовая доменная ошибка."""


class InsufficientBalanceError(SeatBotError):
    def __init__(self, required: float, available: float) -> None:
        super().__init__(f"Insufficient balance: required {required}, available {available}")
        self.required = required
        self.available = available


class NoFreeSeatsError(SeatBotError):
    def __init__(self, ride_id: int) -> None:
        super().__init__(f"No free seats for ride {ride_id}")
        self.ride_id = ride_id


class UserBannedError(SeatBotError):
    def __init__(self, user_id: int) -> None:
        super().__init__(f"User {user_id} is banned")
        self.user_id = user_id


class RideNotBookableError(SeatBotError):
    def __init__(self, ride_id: int, reason: str) -> None:
        super().__init__(f"Ride {ride_id} not bookable: {reason}")
        self.ride_id = ride_id
        self.reason = reason


class AlreadyBookedError(SeatBotError):
    def __init__(self, ride_id: int, user_id: int) -> None:
        super().__init__(f"User {user_id} already booked ride {ride_id}")
        self.ride_id = ride_id
        self.user_id = user_id


class BookingNotFoundError(SeatBotError):
    pass


class RideNotFoundError(SeatBotError):
    pass


class UserNotFoundError(SeatBotError):
    pass


class InvalidInputError(SeatBotError):
    pass
