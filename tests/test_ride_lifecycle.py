import pytest

from kologo.domain.exceptions import NoFreeSeatsError, RideNotBookableError
from kologo.domain.schemas import BookingStatus, RideStatus, TransactionType
from tests.conftest import ServiceFixture
from tests.factories import make_booking, make_ride, make_user


async def test_book_ride_creates_pending(fx: ServiceFixture) -> None:
    fx.rides.add(make_ride(ride_id=1))
    booking = await fx.service.book_ride(1, make_user(1))
    assert booking.status == BookingStatus.PENDING


async def test_book_ride_auto_approves_when_enabled(fx: ServiceFixture) -> None:
    fx.rides.add(make_ride(ride_id=1, auto_approve=True))
    booking = await fx.service.book_ride(1, make_user(1))
    assert booking.status == BookingStatus.APPROVED


async def test_book_ride_auto_approves_vip(fx: ServiceFixture) -> None:
    fx.rides.add(make_ride(ride_id=1, auto_approve=False))
    booking = await fx.service.book_ride(1, make_user(1, is_vip=True))
    assert booking.status == BookingStatus.APPROVED


async def test_book_ride_raises_on_closed_ride(fx: ServiceFixture) -> None:
    fx.rides.add(make_ride(ride_id=1, status=RideStatus.CLOSED))
    with pytest.raises(RideNotBookableError):
        await fx.service.book_ride(1, make_user(1))


async def test_book_ride_missing_ride(fx: ServiceFixture) -> None:
    with pytest.raises(RideNotBookableError):
        await fx.service.book_ride(404, make_user(1))


async def test_book_ride_sends_admin_log(fx: ServiceFixture) -> None:
    fx.rides.add(make_ride(ride_id=1))
    await fx.service.book_ride(1, make_user(1))
    assert fx.bot.admin_logs


async def test_approve_booking_approves_pending(fx: ServiceFixture) -> None:
    fx.rides.add(make_ride(ride_id=1))
    fx.users.add(make_user(1))
    booking = fx.bookings.add(make_booking(ride_id=1, user_id=1))

    result = await fx.service.approve_booking(booking.booking_id)

    assert result is not None
    assert result.status == BookingStatus.APPROVED


async def test_approve_booking_raises_when_full(fx: ServiceFixture) -> None:
    fx.rides.add(make_ride(ride_id=1, seats_total=1))
    fx.bookings.add(make_booking(10, ride_id=1, user_id=2, status=BookingStatus.APPROVED))
    booking = fx.bookings.add(make_booking(11, ride_id=1, user_id=1))

    with pytest.raises(NoFreeSeatsError):
        await fx.service.approve_booking(booking.booking_id)


async def test_approve_booking_returns_none_for_non_pending(fx: ServiceFixture) -> None:
    booking = fx.bookings.add(make_booking(status=BookingStatus.REJECTED))
    assert await fx.service.approve_booking(booking.booking_id) is None


async def test_approve_booking_auto_rejects_overflow_pending(fx: ServiceFixture) -> None:
    fx.rides.add(make_ride(ride_id=1, seats_total=1))
    fx.users.add(make_user(1))
    fx.users.add(make_user(2))
    first = fx.bookings.add(make_booking(10, ride_id=1, user_id=1))
    second = fx.bookings.add(make_booking(11, ride_id=1, user_id=2))

    await fx.service.approve_booking(first.booking_id)

    assert first.status == BookingStatus.APPROVED
    assert second.status == BookingStatus.CANCELLED
    assert fx.bot.texts_for(2)


async def test_complete_ride_charges_paying_passenger(fx: ServiceFixture) -> None:
    fx.rides.add(make_ride(ride_id=1, price=10.0))
    user = fx.users.add(make_user(1, balance=50.0))
    fx.bookings.add(make_booking(10, ride_id=1, user_id=1, status=BookingStatus.APPROVED))

    result = await fx.service.complete_ride(1)

    assert result is not None
    assert result.status == RideStatus.COMPLETED
    assert user.balance == 40.0
    tx = fx.transactions.transactions[-1]
    assert tx.type == TransactionType.RIDE_PAYMENT
    assert tx.amount == 10.0
    booking = await fx.bookings.get_by_id(10)
    assert booking is not None
    assert booking.status == BookingStatus.COMPLETED
    assert booking.paid_amount == 10.0


async def test_complete_ride_vip_pays_nothing(fx: ServiceFixture) -> None:
    fx.rides.add(make_ride(ride_id=1, price=10.0))
    user = fx.users.add(make_user(1, balance=50.0, is_vip=True))
    fx.bookings.add(make_booking(10, ride_id=1, user_id=1, status=BookingStatus.APPROVED))

    await fx.service.complete_ride(1)

    assert user.balance == 50.0
    assert fx.transactions.transactions == []


async def test_complete_ride_free_ride_charges_nothing(fx: ServiceFixture) -> None:
    fx.rides.add(make_ride(ride_id=1, price=0.0))
    user = fx.users.add(make_user(1, balance=50.0))
    fx.bookings.add(make_booking(10, ride_id=1, user_id=1, status=BookingStatus.APPROVED))

    await fx.service.complete_ride(1)

    assert user.balance == 50.0
    assert fx.transactions.transactions == []


async def test_complete_ride_completes_even_when_balance_insufficient(fx: ServiceFixture) -> None:
    fx.rides.add(make_ride(ride_id=1, price=10.0))
    fx.users.add(make_user(1, balance=3.0))
    fx.bookings.add(make_booking(10, ride_id=1, user_id=1, status=BookingStatus.APPROVED))

    await fx.service.complete_ride(1)

    booking = await fx.bookings.get_by_id(10)
    assert booking is not None
    assert booking.status == BookingStatus.COMPLETED
    assert booking.paid_amount == 0.0
    assert fx.transactions.transactions == []


async def test_complete_ride_cancels_pending_bookings(fx: ServiceFixture) -> None:
    fx.rides.add(make_ride(ride_id=1))
    fx.users.add(make_user(1))
    fx.bookings.add(make_booking(10, ride_id=1, user_id=1, status=BookingStatus.PENDING))

    await fx.service.complete_ride(1)

    booking = await fx.bookings.get_by_id(10)
    assert booking is not None
    assert booking.status == BookingStatus.CANCELLED


async def test_complete_ride_ignores_finished_ride(fx: ServiceFixture) -> None:
    fx.rides.add(make_ride(ride_id=1, status=RideStatus.COMPLETED))
    assert await fx.service.complete_ride(1) is None


async def test_complete_ride_ignores_cancelled_ride(fx: ServiceFixture) -> None:
    fx.rides.add(make_ride(ride_id=1, status=RideStatus.CANCELLED))
    assert await fx.service.complete_ride(1) is None


async def test_complete_ride_works_for_in_progress(fx: ServiceFixture) -> None:
    fx.rides.add(make_ride(ride_id=1, status=RideStatus.IN_PROGRESS))
    result = await fx.service.complete_ride(1)
    assert result is not None
    assert result.status == RideStatus.COMPLETED


async def test_complete_ride_notifies_admin_and_passenger(fx: ServiceFixture) -> None:
    fx.rides.add(make_ride(ride_id=1, price=10.0))
    fx.users.add(make_user(1, balance=50.0))
    fx.bookings.add(make_booking(10, ride_id=1, user_id=1, status=BookingStatus.APPROVED))

    await fx.service.complete_ride(1)

    assert fx.bot.admin_logs
    assert fx.bot.texts_for(1)
