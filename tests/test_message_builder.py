from seatbot.domain.schemas import BookingStatus, RideStatus
from seatbot.infrastructure.notifications import MessageBuilder, fmt_amount, fmt_duration
from tests.factories import make_booking, make_ride


def test_fmt_amount_integer() -> None:
    assert fmt_amount(10.0) == "10"


def test_fmt_amount_decimal() -> None:
    assert fmt_amount(10.5) == "10.50"


def test_fmt_duration_minutes() -> None:
    assert fmt_duration(2700) == "45 мин"


def test_fmt_duration_hours() -> None:
    assert fmt_duration(5400) == "1 ч 30 мин"


def test_payment_short_free(messages: MessageBuilder) -> None:
    assert messages.payment_short(0, 10.0, is_free=True) == "бесплатно"


def test_payment_short_deposit(messages: MessageBuilder) -> None:
    assert "деп" in messages.payment_short(10.0, 10.0, is_free=False)


def test_payment_short_by_fact(messages: MessageBuilder) -> None:
    assert "по факту" in messages.payment_short(0, 10.0, is_free=False)


def test_payment_full_variants(messages: MessageBuilder) -> None:
    assert "Бесплатно" in messages.payment_full(0, 10.0, is_free=True)
    assert "Списано с депозита" in messages.payment_full(10.0, 10.0, is_free=False)
    assert "по факту" in messages.payment_full(0, 10.0, is_free=False)


def test_departure_lines_planned_only(messages: MessageBuilder) -> None:
    lines = messages.departure_lines(make_ride())
    assert len(lines) == 1
    assert "Отправление" in lines[0]


def test_departure_lines_with_actual(messages: MessageBuilder) -> None:
    lines = messages.departure_lines(make_ride(started_ago_minutes=5))
    assert len(lines) == 2
    assert "план" in lines[0]
    assert "Выехали" in lines[1]


def test_track_stats_empty_without_track(messages: MessageBuilder) -> None:
    assert messages.track_stats_lines(make_ride()) == []


def test_track_stats_empty_without_finish(messages: MessageBuilder) -> None:
    assert messages.track_stats_lines(make_ride(started_ago_minutes=10)) == []


def test_track_stats_full(messages: MessageBuilder) -> None:
    ride = make_ride(
        started_ago_minutes=40,
        finished_ago_minutes=10,
        track_distance_m=30_000,
        track_max_speed_mps=25.0,
    )
    lines = messages.track_stats_lines(ride)
    assert any("30 мин" in line for line in lines)
    assert any("30.0 км" in line for line in lines)
    assert any("60 км/ч" in line for line in lines)
    assert any("90 км/ч" in line for line in lines)


def test_track_stats_no_max_speed_line_when_zero(messages: MessageBuilder) -> None:
    ride = make_ride(started_ago_minutes=40, finished_ago_minutes=10, track_distance_m=30_000)
    assert not any("Макс" in line for line in messages.track_stats_lines(ride))


def test_rejected_notification_with_refund(messages: MessageBuilder) -> None:
    text = messages.booking_rejected_notification(make_ride(), paid_amount=10.0)
    assert "возвращён" in text


def test_rejected_notification_free_ride(messages: MessageBuilder) -> None:
    text = messages.booking_rejected_notification(make_ride(price=0), paid_amount=0)
    assert "бесплатн" in text


def test_rejected_notification_by_fact_no_refund_claim(messages: MessageBuilder) -> None:
    text = messages.booking_rejected_notification(make_ride(price=10), paid_amount=0)
    assert "по факту" in text
    assert "возвращён" not in text


def test_completed_notification_free(messages: MessageBuilder) -> None:
    text = messages.ride_completed_notification(make_ride(price=0), is_free=True)
    assert "бесплатн" in text


def test_completed_notification_deposit(messages: MessageBuilder) -> None:
    text = messages.ride_completed_notification(make_ride(), paid_amount=10.0, price=10.0)
    assert "Списано с депозита" in text


def test_completed_notification_by_fact(messages: MessageBuilder) -> None:
    text = messages.ride_completed_notification(make_ride(), paid_amount=0, price=10.0)
    assert "по факту" in text


def test_booking_card_shows_status(messages: MessageBuilder) -> None:
    booking = make_booking(status=BookingStatus.APPROVED)
    text = messages.booking_card(booking, make_ride())
    assert "Одобрено" in text


def test_booking_card_completed_ride_has_stats(messages: MessageBuilder) -> None:
    booking = make_booking(status=BookingStatus.COMPLETED)
    ride = make_ride(
        status=RideStatus.COMPLETED,
        started_ago_minutes=40,
        finished_ago_minutes=10,
        track_distance_m=5000,
    )
    text = messages.booking_card(booking, ride)
    assert "В пути" in text
