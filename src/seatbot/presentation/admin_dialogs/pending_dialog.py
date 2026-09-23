from typing import Any

from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import (Button, Cancel, Row, ScrollingGroup, Select,
                                        SwitchTo)
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from seatbot.application.services.ride import RideService
from seatbot.domain.exceptions import NoFreeSeatsError
from seatbot.domain.schemas import BookingStatus
from seatbot.infrastructure.database.dao import BookingsDAO, UsersDAO
from seatbot.infrastructure.notifications import MessageBuilder, route_str, user_display
from seatbot.infrastructure.time import LocalClock

from ..user_dialogs.states import PendingSG, RidesMgmtSG


@inject
async def get_pending_list(
    dialog_manager: DialogManager,
    ride_service: FromDishka[RideService],
    users_dao: FromDishka[UsersDAO],
    clock: FromDishka[LocalClock],
    **_kwargs: Any,
) -> dict[str, Any]:
    pending = await ride_service.list_pending_bookings()
    if not pending:
        return {"has_pending": False, "header": "⏳ <b>Заявки</b>\n\n✨ Заявок нет — всё разобрано."}
    items = []
    for b in pending:
        rws = await ride_service.get_ride_stats(b.ride_id)
        user = await users_dao.get_by_id(b.user_id)
        if not rws:
            continue
        ride = rws.ride
        counts = await ride_service.user_booking_counts(b.user_id)
        no_show = counts.get(BookingStatus.NO_SHOW, 0)
        uname = user_display(user.username, user.first_name, b.user_id) if user else f"id{b.user_id}"
        vip = "⭐" if user and user.is_vip else ""
        items.append(
            {
                "booking_id": b.booking_id,
                "title": (
                    f"{clock.fmt(ride.departure_at, '%d.%m %H:%M')} • {uname}{vip} • "
                    f"🧾{counts.get(BookingStatus.COMPLETED, 0)}" + (f" 🙅{no_show}" if no_show else "")
                ),
            }
        )
    return {
        "has_pending": True,
        "pending": items,
        "header": f"⏳ <b>Заявки: {len(items)}</b>\n\n🧾 — завершённых поездок, 🙅 — неявок.",
    }


@inject
async def get_pending_detail(
    dialog_manager: DialogManager,
    bookings_dao: FromDishka[BookingsDAO],
    ride_service: FromDishka[RideService],
    users_dao: FromDishka[UsersDAO],
    messages: FromDishka[MessageBuilder],
    clock: FromDishka[LocalClock],
    **_kwargs: Any,
) -> dict[str, Any]:
    booking = await bookings_dao.get_by_id(dialog_manager.dialog_data.get("booking_id", 0))
    if not booking or booking.status != BookingStatus.PENDING:
        return {"detail_text": "Заявка уже обработана.", "is_pending": False, "can_approve": False}
    rws = await ride_service.get_ride_stats(booking.ride_id)
    user = await users_dao.get_by_id(booking.user_id)
    if not rws or not user:
        return {"detail_text": "🚫 Заявка не найдена", "is_pending": False, "can_approve": False}
    ride = rws.ride
    dialog_manager.dialog_data["ride_id"] = ride.ride_id
    vip = " ⭐VIP" if user.is_vip else ""
    lines = [
        f"⏳ <b>Заявка #{booking.booking_id}</b>\n",
        f"🚗 {clock.fmt(ride.departure_at)}" + (f" · {route_str(ride)}" if route_str(ride) else ""),
        messages.seats_line(ride, rws.approved_seats, rws.pending_seats),
        "",
        f"👤 {user_display(user.username, user.first_name, user.user_id)}{vip} ({user.user_id})",
        messages.user_brief(user, await ride_service.user_booking_counts(user.user_id)),
    ]
    if rws.free_seats <= 0:
        lines.append("\n⛔ Мест нет — одобрить нельзя")
    return {"detail_text": "\n".join(lines), "is_pending": True, "can_approve": rws.free_seats > 0}


async def on_pending_selected(
    callback: CallbackQuery, select: Select, manager: DialogManager, item_id: str
) -> None:
    manager.dialog_data["booking_id"] = int(item_id)
    await manager.switch_to(PendingSG.detail)


@inject
async def on_approve(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    ride_service: FromDishka[RideService],
) -> None:
    try:
        booking = await ride_service.approve_booking(manager.dialog_data["booking_id"])
    except NoFreeSeatsError:
        await callback.answer("Все места уже заняты — одобрить нельзя", show_alert=True)
        return
    await callback.answer("✅ Одобрено" if booking else "Заявка уже обработана")
    await manager.switch_to(PendingSG.list)


@inject
async def on_reject(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    ride_service: FromDishka[RideService],
) -> None:
    booking = await ride_service.reject_booking(manager.dialog_data["booking_id"])
    await callback.answer("❌ Отклонено" if booking else "Заявка уже обработана")
    await manager.switch_to(PendingSG.list)


async def on_to_ride(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    await manager.start(RidesMgmtSG.ride_detail, data={"ride_id": manager.dialog_data["ride_id"]})


pending_dialog = Dialog(
    Window(
        Format("{header}"),
        ScrollingGroup(
            Select(
                Format("{item[title]}"),
                id="pending_sel",
                item_id_getter=lambda item: str(item["booking_id"]),
                items="pending",
                on_click=on_pending_selected,
            ),
            width=1,
            height=8,
            id="pending_scroll",
            when="has_pending",
        ),
        Cancel(Const("⬅️ В панель")),
        state=PendingSG.list,
        getter=get_pending_list,
    ),
    Window(
        Format("{detail_text}"),
        Row(
            Button(Const("✅ Одобрить"), id="approve", on_click=on_approve, when="can_approve"),
            Button(Const("❌ Отклонить"), id="reject", on_click=on_reject, when="is_pending"),
        ),
        Button(Const("🚗 К поездке"), id="to_ride", on_click=on_to_ride, when="is_pending"),
        SwitchTo(Const("⬅️ К заявкам"), id="back", state=PendingSG.list),
        state=PendingSG.detail,
        getter=get_pending_detail,
    ),
)
