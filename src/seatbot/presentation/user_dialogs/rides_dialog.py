from typing import Any

from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, StartMode, Window
from aiogram_dialog.widgets.kbd import Button, ScrollingGroup, Select, Start, SwitchTo
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from seatbot.application.services.ride import RideService
from seatbot.domain.exceptions import (AlreadyBookedError, NoFreeSeatsError,
                                       RideNotBookableError, SeatBotError,
                                       UserBannedError, VipHoldActiveError)
from seatbot.domain.schemas import BookingStatus, Ride, RideWithStats, User
from seatbot.infrastructure.database.dao import BookingsDAO, RidesDAO, UsersDAO
from seatbot.infrastructure.notifications import MessageBuilder, fmt_amount, route_str
from seatbot.infrastructure.time import LocalClock

from .states import MainMenuSG, RidesSG


def booking_error_text(error: SeatBotError) -> str:
    match error:
        case NoFreeSeatsError():
            return "🚫 Мест нет"
        case AlreadyBookedError():
            return "✅ Вы уже забронировали эту поездку"
        case UserBannedError():
            return "⛔ Вы в чёрном списке"
        case VipHoldActiveError(remaining_seconds=remaining):
            mins, secs = divmod(remaining, 60)
            return f"⭐ Сейчас VIP-холд — только VIP могут бронировать. Подождите ещё {mins}:{secs:02d}."
        case RideNotBookableError(reason=reason):
            return f"🚫 Нельзя забронировать: {reason}"
    return "🚫 Бронь недоступна"


def payment_line(ride: Ride, user: User | None) -> str:
    if ride.is_free:
        return ""
    price = float(ride.price)
    if user and user.is_vip:
        return "⭐ Для вас поездка бесплатна (VIP)"
    if user and user.balance >= price:
        return f"💳 После поездки спишется с депозита: <b>{fmt_amount(price)} BYN</b>"
    return f"💵 Оплата по факту поездки: <b>{fmt_amount(price)} BYN</b>"


def seats_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "место"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "места"
    return "мест"


def auto_approved_for(ride: Ride, user: User | None) -> bool:
    return ride.auto_approve or bool(user and user.is_vip)


def queue_line(rws: RideWithStats, user: User | None) -> str:
    if auto_approved_for(rws.ride, user) or rws.free_seats <= 0:
        return ""
    if rws.pending_seats:
        return (
            f"⏳ Заявок в очереди: <b>{rws.pending_seats}</b> на <b>{rws.free_seats}</b> "
            f"{seats_word(rws.free_seats)} — решение за водителем."
        )
    return "⏳ Брони подтверждает водитель."


@inject
async def get_rides_list(
    dialog_manager: DialogManager,
    rides_dao: FromDishka[RidesDAO],
    bookings_dao: FromDishka[BookingsDAO],
    clock: FromDishka[LocalClock],
    **_kwargs: Any,
) -> dict[str, Any]:
    rides = await rides_dao.list_upcoming_visible()
    user_id = dialog_manager.middleware_data["event_from_user"].id
    my_status = {
        b.ride_id: b.status
        for b in await bookings_dao.list_for_user(user_id, limit=100)
        if b.status in (BookingStatus.PENDING, BookingStatus.APPROVED)
    }
    if not rides:
        return {
            "has_rides": False,
            "empty_text": "🚫 Сейчас нет запланированных поездок. Загляни позже!",
            "back_btn": "⬅️ В меню",
        }
    items = []
    for rws in rides:
        route = route_str(rws.ride)
        route_part = f" • {route}" if route else ""
        price = "бесплатно" if rws.ride.is_free else f"{fmt_amount(rws.ride.price)} BYN"
        status = my_status.get(rws.ride.ride_id)
        mark = "✅ " if status == BookingStatus.APPROVED else "⏳ " if status == BookingStatus.PENDING else ""
        items.append(
            {
                "ride_id": rws.ride.ride_id,
                "title": (
                    f"{mark}{clock.fmt(rws.ride.departure_at, '%d.%m %H:%M')} • {price} • "
                    f"{rws.free_seats}/{rws.ride.seats_total} мест{route_part}"
                ),
            }
        )
    return {
        "has_rides": True,
        "rides": items,
        "back_btn": "⬅️ В меню",
    }


@inject
async def get_ride_detail(
    dialog_manager: DialogManager,
    rides_dao: FromDishka[RidesDAO],
    bookings_dao: FromDishka[BookingsDAO],
    users_dao: FromDishka[UsersDAO],
    messages: FromDishka[MessageBuilder],
    clock: FromDishka[LocalClock],
    ride_service: FromDishka[RideService],
    **_kwargs: Any,
) -> dict[str, Any]:
    ride_id: int = dialog_manager.dialog_data["ride_id"]
    rws = await rides_dao.get_with_stats(ride_id)
    if not rws:
        return {"ride_text": "🚫 Поездка не найдена", "back_btn": "⬅️ Назад"}

    user_id = dialog_manager.middleware_data["event_from_user"].id
    user = await users_dao.get_by_id(user_id)
    existing = await bookings_dao.get_by_ride_and_user(ride_id, user_id)

    ride_text = messages.ride_card(rws)
    now = clock.now()
    hold_active = rws.ride.is_vip_hold_active(now)
    is_vip = bool(user and user.is_vip)
    if hold_active and not is_vip:
        remaining = rws.ride.vip_hold_remaining_seconds(now)
        mins, secs = divmod(remaining, 60)
        ride_text += (
            f"\n\n⭐ <b>Бронь временно только для VIP</b>\n"
            f"Обычные пользователи смогут забронировать через "
            f"<b>{mins}:{secs:02d}</b>\n"
            f"<i>Станьте VIP, чтобы бронировать сразу — кнопка в главном меню.</i>"
        )
    payment = payment_line(rws.ride, user)
    if payment:
        ride_text += f"\n{payment}"
    queue = queue_line(rws, user)
    if queue and not existing:
        ride_text += f"\n\n{queue}"
    error = await ride_service.booking_error(rws.ride, user) if user else None
    can_book = user is not None and error is None
    if user is None:
        blocked_text = "Сначала нажмите /start"
    elif isinstance(error, VipHoldActiveError):
        blocked_text = "⭐ Бронь пока только для VIP"
    else:
        blocked_text = booking_error_text(error) if error else ""

    has_origin_geo = (
        existing is not None
        and existing.status == BookingStatus.APPROVED
        and rws.ride.origin_lat is not None
        and rws.ride.origin_lon is not None
    )
    return {
        "ride_text": ride_text,
        "ride_id": ride_id,
        "can_book": can_book,
        "blocked_text": blocked_text,
        "has_origin_geo": has_origin_geo,
        "book_btn": "🪑 Забронировать",
        "origin_btn": "📍 Место отправления",
        "back_btn": "⬅️ К поездкам",
    }


async def on_rides_start(start_data: Any, manager: DialogManager) -> None:
    if isinstance(start_data, dict) and "ride_id" in start_data:
        manager.dialog_data["ride_id"] = start_data["ride_id"]


async def on_ride_selected(
    callback: CallbackQuery,
    select: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    manager.dialog_data["ride_id"] = int(item_id)
    await manager.next()


@inject
async def get_book_confirm(
    dialog_manager: DialogManager,
    rides_dao: FromDishka[RidesDAO],
    users_dao: FromDishka[UsersDAO],
    messages: FromDishka[MessageBuilder],
    ride_service: FromDishka[RideService],
    **_kwargs: Any,
) -> dict[str, Any]:
    ride_id: int = dialog_manager.dialog_data["ride_id"]
    rws = await rides_dao.get_with_stats(ride_id)
    user = await users_dao.get_by_id(dialog_manager.middleware_data["event_from_user"].id)
    if not rws or not user:
        return {"confirm_text": "🚫 Поездка не найдена", "can_confirm": False}
    ride = rws.ride
    error = await ride_service.booking_error(ride, user)
    lines = ["📝 <b>Подтвердите бронь</b>\n", *messages.departure_lines(ride)]
    route = route_str(ride)
    if route:
        lines.append(f"📍 Маршрут: <b>{route}</b>")
    lines.append(payment_line(ride, user) or "💰 Поездка бесплатная")
    lines.append("")
    if error:
        lines.append(booking_error_text(error))
    elif auto_approved_for(ride, user):
        lines.append("⚡ Место закрепится за вами сразу после подтверждения.")
    else:
        lines.append(
            "⏳ Заявку рассмотрит водитель. "
            f"Сейчас заявок: <b>{rws.pending_seats}</b>, свободных мест: <b>{rws.free_seats}</b>.\n"
            "Если места займут раньше — заявка отклонится автоматически, ничего не спишется."
        )
    lines.append("\n<i>Отменить бронь можно в «Мои брони» до отправления.</i>")
    return {"confirm_text": "\n".join(lines), "can_confirm": error is None}


@inject
async def on_book_click(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    ride_service: FromDishka[RideService],
    rides_dao: FromDishka[RidesDAO],
    users_dao: FromDishka[UsersDAO],
) -> None:
    ride_id: int = manager.dialog_data["ride_id"]
    user_id = manager.middleware_data["event_from_user"].id
    user = await users_dao.get_by_id(user_id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return
    try:
        booking = await ride_service.book_ride(ride_id, user)
    except SeatBotError as e:
        await callback.answer(booking_error_text(e), show_alert=True)
        await manager.switch_to(RidesSG.detail)
        return

    await callback.answer(
        "✅ Место закреплено!"
        if booking.status == BookingStatus.APPROVED
        else "⏳ Заявка отправлена водителю — ответ придёт сообщением.",
        show_alert=True,
    )
    await manager.start(MainMenuSG.main, mode=StartMode.RESET_STACK)


@inject
async def on_show_origin(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    rides_dao: FromDishka[RidesDAO],
) -> None:
    ride_id: int = manager.dialog_data["ride_id"]
    ride = await rides_dao.get_by_id(ride_id)
    if not ride or ride.origin_lat is None or ride.origin_lon is None:
        await callback.answer("Геопозиция не задана", show_alert=True)
        return
    if callback.message:
        await callback.message.answer_location(
            latitude=ride.origin_lat,
            longitude=ride.origin_lon,
        )
    await callback.answer()


rides_dialog = Dialog(
    Window(
        Const("🚗 <b>Ближайшие поездки</b>\n\nВыберите поездку:"),
        ScrollingGroup(
            Select(
                Format("{item[title]}"),
                id="rides_sel",
                item_id_getter=lambda item: str(item["ride_id"]),
                items="rides",
                on_click=on_ride_selected,
                when="has_rides",
            ),
            width=1,
            height=8,
            id="rides_scroll",
        ),
        Format("{empty_text}", when="not has_rides"),
        Start(Format("{back_btn}"), id="to_menu", state=MainMenuSG.main, mode=StartMode.RESET_STACK),
        state=RidesSG.list,
        getter=get_rides_list,
    ),
    Window(
        Format("{ride_text}"),
        SwitchTo(Format("{book_btn}"), id="book", state=RidesSG.book_confirm, when="can_book"),
        Format("{blocked_text}", when="blocked_text"),
        Button(Format("{origin_btn}"), id="show_origin", on_click=on_show_origin, when="has_origin_geo"),
        SwitchTo(Format("{back_btn}"), id="back", state=RidesSG.list),
        state=RidesSG.detail,
        getter=get_ride_detail,
    ),
    Window(
        Format("{confirm_text}"),
        Button(Const("✅ Подтвердить"), id="confirm_book", on_click=on_book_click, when="can_confirm"),
        SwitchTo(Const("⬅️ Назад"), id="back", state=RidesSG.detail),
        state=RidesSG.book_confirm,
        getter=get_book_confirm,
    ),
    on_start=on_rides_start,
)
