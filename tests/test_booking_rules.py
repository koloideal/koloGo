
from seatbot.domain.exceptions import (AlreadyBookedError, NoFreeSeatsError,
                                       RideNotBookableError, UserBannedError,
                                       VipHoldActiveError)
from seatbot.domain.schemas import BookingStatus, RideStatus, TransactionType
from tests.conftest import ServiceFixture
from tests.factories import make_booking, make_ride, make_user


async def test_booking_error_closed_ride(fx: ServiceFixture) -> None:
    ride = make_ride(status=RideStatus.CLOSED)
    error = await fx.service.booking_error(ride, make_user())
    assert isinstance(error, RideNotBookableError)


async def test_booking_error_departed_ride(fx: ServiceFixture) -> None:
    ride = make_ride(departure_in_minutes=-5)
    error = await fx.service.booking_error(ride, make_user())
    assert isinstance(error, RideNotBookableError)


async def test_booking_error_hidden_ride(fx: ServiceFixture) -> None:
    ride = make_ride(is_visible=False)
    error = await fx.service.booking_error(ride, make_user())
    assert isinstance(error, RideNotBookableError)


async def test_booking_error_banned_user(fx: ServiceFixture) -> None:
    error = await fx.service.booking_error(make_ride(), make_user(is_banned=True))
    assert isinstance(error, UserBannedError)


async def test_booking_error_already_booked(fx: ServiceFixture) -> None:
    fx.bookings.add(make_booking(ride_id=1, user_id=1))
    error = await fx.service.booking_error(make_ride(ride_id=1), make_user(1))
    assert isinstance(error, AlreadyBookedError)


async def test_booking_error_previously_rejected(fx: ServiceFixture) -> None:
    fx.bookings.add(make_booking(ride_id=1, user_id=1, status=BookingStatus.REJECTED))
    error = await fx.service.booking_error(make_ride(ride_id=1), make_user(1))
    assert isinstance(error, RideNotBookableError)


async def test_booking_error_vip_hold_for_regular_user(fx: ServiceFixture) -> None:
    ride = make_ride(vip_hold_minutes=15)
    error = await fx.service.booking_error(ride, make_user())
    assert isinstance(error, VipHoldActiveError)


async def test_booking_error_vip_hold_ignored_for_vip(fx: ServiceFixture) -> None:
    ride = make_ride(vip_hold_minutes=15)
    error = await fx.service.booking_error(ride, make_user(is_vip=True))
    assert error is None


async def test_booking_error_full_ride(fx: ServiceFixture) -> None:
    ride = fx.rides.add(make_ride(ride_id=1, seats_total=1))
    fx.bookings.add(make_booking(ride_id=1, user_id=2, status=BookingStatus.APPROVED))
    error = await fx.service.booking_error(ride, make_user(1))
    assert isinstance(error, NoFreeSeatsError)


async def test_booking_error_ok(fx: ServiceFixture) -> None:
    assert await fx.service.booking_error(make_ride(), make_user()) is None


def test_can_user_cancel_pending_on_open(fx: ServiceFixture) -> None:
    booking = make_booking(status=BookingStatus.PENDING)
    assert fx.service.can_user_cancel(booking, make_ride())


def test_can_user_cancel_pending_on_closed(fx: ServiceFixture) -> None:
    booking = make_booking(status=BookingStatus.PENDING)
    assert fx.service.can_user_cancel(booking, make_ride(status=RideStatus.CLOSED))


def test_can_user_cancel_pending_not_on_completed(fx: ServiceFixture) -> None:
    booking = make_booking(status=BookingStatus.PENDING)
    assert not fx.service.can_user_cancel(booking, make_ride(status=RideStatus.COMPLETED))


def test_can_user_cancel_approved_before_departure(fx: ServiceFixture) -> None:
    booking = make_booking(status=BookingStatus.APPROVED)
    assert fx.service.can_user_cancel(booking, make_ride(departure_in_minutes=30))


def test_can_user_cancel_approved_after_departure(fx: ServiceFixture) -> None:
    booking = make_booking(status=BookingStatus.APPROVED)
    assert not fx.service.can_user_cancel(booking, make_ride(departure_in_minutes=-30))


async def test_cancel_by_user_refunds_paid_deposit(fx: ServiceFixture) -> None:
    fx.rides.add(make_ride(ride_id=1))
    user = fx.users.add(make_user(1, balance=50.0))
    booking = fx.bookings.add(make_booking(ride_id=1, user_id=1, paid_amount=10.0))

    result = await fx.service.cancel_booking_by_user(booking.booking_id, 1)

    assert result is not None
    assert result.status == BookingStatus.CANCELLED
    assert user.balance == 60.0
    refund = fx.transactions.transactions[-1]
    assert refund.type == TransactionType.REFUND
    assert refund.amount == 10.0
    assert refund.ride_id == 1


async def test_cancel_by_user_no_refund_without_payment(fx: ServiceFixture) -> None:
    fx.rides.add(make_ride(ride_id=1))
    user = fx.users.add(make_user(1, balance=50.0))
    booking = fx.bookings.add(make_booking(ride_id=1, user_id=1, paid_amount=0.0))

    result = await fx.service.cancel_booking_by_user(booking.booking_id, 1)

    assert result is not None
    assert user.balance == 50.0
    assert fx.transactions.transactions == []


async def test_cancel_by_user_rejects_wrong_user(fx: ServiceFixture) -> None:
    fx.rides.add(make_ride(ride_id=1))
    booking = fx.bookings.add(make_booking(ride_id=1, user_id=1))
    assert await fx.service.cancel_booking_by_user(booking.booking_id, user_id=999) is None


async def test_cancel_by_user_rejects_completed_booking(fx: ServiceFixture) -> None:
    fx.rides.add(make_ride(ride_id=1, status=RideStatus.COMPLETED))
    booking = fx.bookings.add(
        make_booking(ride_id=1, user_id=1, status=BookingStatus.COMPLETED)
    )
    assert await fx.service.cancel_booking_by_user(booking.booking_id, 1) is None


async def test_reject_booking_rejects_and_notifies(fx: ServiceFixture) -> None:
    fx.rides.add(make_ride(ride_id=1))
    booking = fx.bookings.add(make_booking(ride_id=1, user_id=1, paid_amount=10.0))

    result = await fx.service.reject_booking(booking.booking_id)

    assert result is not None
    assert result.status == BookingStatus.REJECTED
    assert "возвращён" in fx.bot.texts_for(1)[-1]


async def test_reject_booking_skips_non_pending(fx: ServiceFixture) -> None:
    booking = fx.bookings.add(make_booking(status=BookingStatus.APPROVED))
    assert await fx.service.reject_booking(booking.booking_id) is None


async def test_kick_booking_refunds_deposit(fx: ServiceFixture) -> None:
    fx.rides.add(make_ride(ride_id=1))
    user = fx.users.add(make_user(1, balance=50.0))
    booking = fx.bookings.add(
        make_booking(ride_id=1, user_id=1, status=BookingStatus.APPROVED, paid_amount=10.0)
    )

    result = await fx.service.kick_booking(booking.booking_id, "нарушение правил")

    assert result is not None
    assert result.status == BookingStatus.CANCELLED
    assert user.balance == 60.0
    assert fx.transactions.transactions[-1].type == TransactionType.REFUND


async def test_kick_booking_no_refund_by_fact(fx: ServiceFixture) -> None:
    fx.rides.add(make_ride(ride_id=1))
    user = fx.users.add(make_user(1, balance=50.0))
    booking = fx.bookings.add(
        make_booking(ride_id=1, user_id=1, status=BookingStatus.APPROVED, paid_amount=0.0)
    )

    result = await fx.service.kick_booking(booking.booking_id, "нарушение правил")

    assert result is not None
    assert user.balance == 50.0
    assert fx.transactions.transactions == []


async def test_mark_no_show_only_approved(fx: ServiceFixture) -> None:
    fx.rides.add(make_ride(ride_id=1, status=RideStatus.IN_PROGRESS))
    booking = fx.bookings.add(make_booking(ride_id=1, user_id=1, status=BookingStatus.PENDING))
    assert await fx.service.mark_no_show(booking.booking_id) is None


async def test_mark_no_show_marks_approved(fx: ServiceFixture) -> None:
    fx.rides.add(make_ride(ride_id=1, status=RideStatus.IN_PROGRESS))
    booking = fx.bookings.add(make_booking(ride_id=1, user_id=1, status=BookingStatus.APPROVED))

    result = await fx.service.mark_no_show(booking.booking_id)

    assert result is not None
    assert result.status == BookingStatus.NO_SHOW
    assert "не явились" in fx.bot.texts_for(1)[-1]
