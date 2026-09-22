from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import Button, Cancel, ScrollingGroup, Select, SwitchTo
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from seatbot.application.services.ride import RideService
from seatbot.domain.schemas import BookingStatus
from seatbot.infrastructure.database.dao import BookingsDAO, RidesDAO, UsersDAO
from seatbot.infrastructure.notifications import MessageBuilder
from seatbot.infrastructure.time import LocalClock

from .states import MyBookingsSG

_STATUS_EMOJI = {
    BookingStatus.PENDING: "⏳",
    BookingStatus.APPROVED: "✅",
    BookingStatus.REJECTED: "❌",
    BookingStatus.CANCELLED: "🚫",
    BookingStatus.COMPLETED: "🏁",
    BookingStatus.NO_SHOW: "🙅",
}


@inject
async def get_my_bookings(
    dialog_manager: DialogManager,
    bookings_dao: FromDishka[BookingsDAO],
    rides_dao: FromDishka[RidesDAO],
    users_dao: FromDishka[UsersDAO],
    messages: FromDishka[MessageBuilder],
    clock: FromDishka[LocalClock],
    **_kwargs,
):
    user_id = dialog_manager.middleware_data["event_from_user"].id
    user = await users_dao.get_by_id(user_id)
    is_vip = bool(user and user.is_vip)
    bookings = await bookings_dao.list_for_user(user_id, limit=100)
    if not bookings:
        return {
            "has_bookings": False,
            "empty_text": "🚫 У вас пока нет броней.",
            "back_btn": "⬅️ В меню",
        }
    items = []
    for b in bookings:
        ride = await rides_dao.get_by_id(b.ride_id)
        if not ride:
            continue
        emoji = _STATUS_EMOJI.get(b.status, "•")
        pay = messages.payment_short(b.paid_amount, float(ride.price), ride.is_free or is_vip)
        items.append(
            {
                "booking_id": b.booking_id,
                "title": (f"{emoji} {clock.fmt(ride.departure_at, '%d.%m %H:%M')} • {pay}"),
            }
        )
    return {
        "has_bookings": True,
        "bookings": items,
        "back_btn": "⬅️ В меню",
    }


@inject
async def get_booking_detail(
    dialog_manager: DialogManager,
    bookings_dao: FromDishka[BookingsDAO],
    rides_dao: FromDishka[RidesDAO],
    users_dao: FromDishka[UsersDAO],
    messages: FromDishka[MessageBuilder],
    **_kwargs,
):
    booking_id: int = dialog_manager.dialog_data["booking_id"]
    booking = await bookings_dao.get_by_id(booking_id)
    if not booking:
        return {"booking_text": "🚫 Бронь не найдена", "back_btn": "⬅️ Назад"}
    ride = await rides_dao.get_by_id(booking.ride_id)
    if not ride:
        return {"booking_text": "🚫 Поездка не найдена", "back_btn": "⬅️ Назад"}
    user = await users_dao.get_by_id(booking.user_id)
    can_cancel = booking.status in (BookingStatus.PENDING, BookingStatus.APPROVED)
    has_origin_geo = (
        booking.status == BookingStatus.APPROVED
        and ride.origin_lat is not None
        and ride.origin_lon is not None
    )
    return {
        "booking_text": messages.booking_card(booking, ride, is_vip=bool(user and user.is_vip)),
        "can_cancel": can_cancel,
        "has_origin_geo": has_origin_geo,
        "cancel_btn": "🚫 Отменить бронь",
        "origin_btn": "📍 Место отправления",
        "back_btn": "⬅️ К броням",
    }


@inject
async def on_show_origin(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    bookings_dao: FromDishka[BookingsDAO],
    rides_dao: FromDishka[RidesDAO],
):
    booking_id: int = manager.dialog_data["booking_id"]
    booking = await bookings_dao.get_by_id(booking_id)
    if not booking:
        await callback.answer("Бронь не найдена", show_alert=True)
        return
    ride = await rides_dao.get_by_id(booking.ride_id)
    if not ride or ride.origin_lat is None or ride.origin_lon is None:
        await callback.answer("Геопозиция не задана", show_alert=True)
        return
    if callback.message:
        await callback.message.answer_location(
            latitude=ride.origin_lat,
            longitude=ride.origin_lon,
        )
    await callback.answer()


@inject
async def on_cancel_booking(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    ride_service: FromDishka[RideService],
):
    booking_id: int = manager.dialog_data["booking_id"]
    user_id = manager.middleware_data["event_from_user"].id
    booking = await ride_service.cancel_booking_by_user(booking_id, user_id)
    if booking:
        await callback.answer("Бронь отменена, депозит возвращён.", show_alert=True)
    else:
        await callback.answer("Не удалось отменить бронь.", show_alert=True)
    await manager.switch_to(MyBookingsSG.list)


async def on_booking_selected(
    callback: CallbackQuery,
    select: Select,
    manager: DialogManager,
    item_id: str,
):
    manager.dialog_data["booking_id"] = int(item_id)
    await manager.next()


my_bookings_dialog = Dialog(
    Window(
        Const("📋 <b>Мои брони</b>"),
        ScrollingGroup(
            Select(
                Format("{item[title]}"),
                id="bookings_sel",
                item_id_getter=lambda item: str(item["booking_id"]),
                items="bookings",
                on_click=on_booking_selected,
                when="has_bookings",
            ),
            width=1,
            height=8,
            id="bookings_scroll",
        ),
        Format("{empty_text}", when="not has_bookings"),
        Cancel(Format("{back_btn}")),
        state=MyBookingsSG.list,
        getter=get_my_bookings,
    ),
    Window(
        Format("{booking_text}"),
        Button(Format("{cancel_btn}"), id="cancel_booking", on_click=on_cancel_booking, when="can_cancel"),
        Button(Format("{origin_btn}"), id="show_origin", on_click=on_show_origin, when="has_origin_geo"),
        SwitchTo(Format("{back_btn}"), id="back", state=MyBookingsSG.list),
        state=MyBookingsSG.detail,
        getter=get_booking_detail,
    ),
)
