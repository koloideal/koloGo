from typing import Any

from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import Button, Group, SwitchTo
from aiogram_dialog.widgets.text import Const, Format, List
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from seatbot.application.services.ride import RideService
from seatbot.domain.schemas import BookingStatus
from seatbot.infrastructure.database.dao import BookingsDAO, RidesDAO, UsersDAO

from ..user_dialogs.states import RideBookingsSG, RidesMgmtSG

_STATUS_EMOJI = {
    BookingStatus.PENDING: "⏳",
    BookingStatus.APPROVED: "✅",
    BookingStatus.REJECTED: "❌",
    BookingStatus.CANCELLED: "🚫",
    BookingStatus.COMPLETED: "🏁",
    BookingStatus.NO_SHOW: "🙅",
}


@inject
async def get_ride_bookings(
    dialog_manager: DialogManager,
    bookings_dao: FromDishka[BookingsDAO],
    users_dao: FromDishka[UsersDAO],
    **_kwargs,
):
    start_data: dict[str, Any] | None = dialog_manager.start_data  # type: ignore[assignment]
    ride_id: int | None = start_data.get("ride_id") if start_data else dialog_manager.dialog_data.get("ride_id")
    if ride_id is None:
        return {"has_bookings": False, "empty_text": "🚫 Нет броней.", "back_btn": "⬅️ Назад"}
    dialog_manager.dialog_data["ride_id"] = ride_id
    bookings = await bookings_dao.list_for_ride(ride_id)
    if not bookings:
        return {"has_bookings": False, "empty_text": "🚫 На эту поездку нет броней.", "back_btn": "⬅️ Назад"}
    items = []
    for b in bookings:
        user = await users_dao.get_by_id(b.user_id)
        emoji = _STATUS_EMOJI.get(b.status, "•")
        vip = " ⭐" if (user and user.is_vip) else ""
        uname = f"@{user.username}" if user and user.username else f"id:{b.user_id}"
        items.append(
            {
                "booking_id": b.booking_id,
                "title": f"{emoji} #{b.booking_id} • {uname}{vip} • {b.status.value} • {b.paid_amount:.2f}",
            }
        )
    return {"has_bookings": True, "bookings": items, "back_btn": "⬅️ К поездке"}


@inject
async def get_booking_detail(
    dialog_manager: DialogManager,
    bookings_dao: FromDishka[BookingsDAO],
    users_dao: FromDishka[UsersDAO],
    rides_dao: FromDishka[RidesDAO],
    **_kwargs,
):
    booking_id: int = dialog_manager.dialog_data["booking_id"]
    booking = await bookings_dao.get_by_id(booking_id)
    if not booking:
        return {"booking_text": "🚫 Бронь не найдена", "back_btn": "⬅️ Назад"}
    user = await users_dao.get_by_id(booking.user_id)
    ride = await rides_dao.get_by_id(booking.ride_id)
    uname = f"@{user.username}" if user and user.username else f"id:{booking.user_id}"
    vip = " ⭐VIP" if (user and user.is_vip) else ""
    text = (
        f"<b>Бронь #{booking.booking_id}</b>\n\n"
        f"👤 Пользователь: {uname}{vip} ({booking.user_id})\n"
        f"🚗 Поездка #{booking.ride_id}"
    )
    if ride:
        text += f" — {ride.departure_at.strftime('%d.%m.%Y %H:%M')}"
    text += f"\n📋 Статус: {_STATUS_EMOJI.get(booking.status, '•')} {booking.status.value}\n💰 Списано: {booking.paid_amount:.2f} BYN"
    is_pending = booking.status == BookingStatus.PENDING
    is_approved = booking.status == BookingStatus.APPROVED
    return {
        "booking_text": text,
        "is_pending": is_pending,
        "is_approved": is_approved,
        "approve_btn": "✅ Одобрить",
        "reject_btn": "❌ Отклонить",
        "noshow_btn": "🙅 No-show",
        "back_btn": "⬅️ К броням",
    }


@inject
async def on_approve(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    ride_service: FromDishka[RideService],
):
    booking_id: int = manager.dialog_data["booking_id"]
    await ride_service.approve_booking(booking_id)
    await callback.answer("Одобрено", show_alert=True)
    await manager.switch_to(RideBookingsSG.bookings_list)


@inject
async def on_reject(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    ride_service: FromDishka[RideService],
):
    booking_id: int = manager.dialog_data["booking_id"]
    await ride_service.reject_booking(booking_id)
    await callback.answer("Отклонено, возврат выполнен", show_alert=True)
    await manager.switch_to(RideBookingsSG.bookings_list)


@inject
async def on_noshow(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    ride_service: FromDishka[RideService],
):
    booking_id: int = manager.dialog_data["booking_id"]
    await ride_service.mark_no_show(booking_id)
    await callback.answer("Отмечено no-show", show_alert=True)
    await manager.switch_to(RideBookingsSG.bookings_list)


ride_detail_dialog = Dialog(
    Window(
        Const("📋 <b>Брони на поездку</b>"),
        List(Format("{item[title]}"), items="bookings", id="bookings_list", when="has_bookings"),
        Format("{empty_text}", when="not has_bookings"),
        SwitchTo(Format("{back_btn}"), id="back", state=RidesMgmtSG.ride_detail),
        state=RideBookingsSG.bookings_list,
        getter=get_ride_bookings,
    ),
    Window(
        Format("{booking_text}"),
        Group(
            Button(Format("{approve_btn}"), id="approve", on_click=on_approve, when="is_pending"),
            Button(Format("{reject_btn}"), id="reject", on_click=on_reject, when="is_pending"),
            Button(Format("{noshow_btn}"), id="noshow", on_click=on_noshow, when="is_approved"),
            width=2,
        ),
        SwitchTo(Format("{back_btn}"), id="back", state=RideBookingsSG.bookings_list),
        state=RideBookingsSG.booking_detail,
        getter=get_booking_detail,
    ),
)
