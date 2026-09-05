from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import Button, Cancel, Select, SwitchTo
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from seatbot.application.services.ride import RideService
from seatbot.domain.schemas import BookingStatus
from seatbot.infrastructure.database.dao import BookingsDAO, RidesDAO
from seatbot.infrastructure.notifications import MessageBuilder

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
    **_kwargs,
):
    user_id = dialog_manager.middleware_data["event_from_user"].id
    bookings = await bookings_dao.list_for_user(user_id, limit=20)
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
        price_str = "бесплатно" if b.paid_amount <= 0 else f"{b.paid_amount:.2f} BYN"
        items.append(
            {
                "booking_id": b.booking_id,
                "title": (
                    f"{emoji} #{b.booking_id} • поездка #{ride.ride_id} • "
                    f"{ride.departure_at.strftime('%d.%m %H:%M')} • {price_str}"
                ),
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
    **_kwargs,
):
    booking_id: int = dialog_manager.dialog_data["booking_id"]
    booking = await bookings_dao.get_by_id(booking_id)
    if not booking:
        return {"booking_text": "🚫 Бронь не найдена", "back_btn": "⬅️ Назад"}
    ride = await rides_dao.get_by_id(booking.ride_id)
    if not ride:
        return {"booking_text": "🚫 Поездка не найдена", "back_btn": "⬅️ Назад"}
    can_cancel = booking.status in (BookingStatus.PENDING, BookingStatus.APPROVED)
    return {
        "booking_text": MessageBuilder.booking_card(booking, ride),
        "can_cancel": can_cancel,
        "cancel_btn": "🚫 Отменить бронь",
        "back_btn": "⬅️ К броням",
    }


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
        Select(
            Format("{item[title]}"),
            id="bookings_sel",
            item_id_getter=lambda item: str(item["booking_id"]),
            items="bookings",
            on_click=on_booking_selected,
            when="has_bookings",
        ),
        Format("{empty_text}", when="not has_bookings"),
        Cancel(Format("{back_btn}")),
        state=MyBookingsSG.list,
        getter=get_my_bookings,
    ),
    Window(
        Format("{booking_text}"),
        Button(Format("{cancel_btn}"), id="cancel_booking", on_click=on_cancel_booking, when="can_cancel"),
        SwitchTo(Format("{back_btn}"), id="back", state=MyBookingsSG.list),
        state=MyBookingsSG.detail,
        getter=get_booking_detail,
    ),
)
