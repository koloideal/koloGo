from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import Button, Cancel, Column, Group, Select, SwitchTo
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from seatbot.application.services.ride import RideService
from seatbot.domain.schemas import RideStatus
from seatbot.infrastructure.database.dao import RidesDAO
from seatbot.infrastructure.notifications import MessageBuilder

from ..user_dialogs.states import RideBookingsSG, RidesMgmtSG

_STATUS_EMOJI = {
    RideStatus.OPEN: "🟢",
    RideStatus.CLOSED: "🟡",
    RideStatus.COMPLETED: "✅",
    RideStatus.CANCELLED: "❌",
}


@inject
async def get_rides_list(
    dialog_manager: DialogManager,
    rides_dao: FromDishka[RidesDAO],
    **_kwargs,
):
    rides = await rides_dao.list_all(limit=30)
    if not rides:
        return {"has_rides": False, "empty_text": "🚫 Поездок пока нет.", "back_btn": "⬅️ В панель"}
    items = []
    for rws in rides:
        emoji = _STATUS_EMOJI.get(rws.ride.status, "•")
        price_str = "бесплатно" if rws.ride.is_free else f"{rws.ride.price:.2f} BYN"
        items.append(
            {
                "ride_id": rws.ride.ride_id,
                "title": (
                    f"{emoji} #{rws.ride.ride_id} • {rws.ride.departure_at.strftime('%d.%m %H:%M')} • "
                    f"{price_str} • {rws.free_seats}/{rws.ride.seats_total} мест"
                ),
            }
        )
    return {"has_rides": True, "rides": items, "back_btn": "⬅️ В панель"}


@inject
async def get_ride_detail(
    dialog_manager: DialogManager,
    rides_dao: FromDishka[RidesDAO],
    **_kwargs,
):
    ride_id: int = dialog_manager.dialog_data["ride_id"]
    rws = await rides_dao.get_with_stats(ride_id)
    if not rws:
        return {"ride_text": "🚫 Поездка не найдена", "back_btn": "⬅️ Назад"}
    is_open = rws.ride.status == RideStatus.OPEN
    is_active = rws.ride.status in (RideStatus.OPEN, RideStatus.CLOSED)
    return {
        "ride_text": MessageBuilder.ride_card(rws),
        "ride_id": ride_id,
        "is_open": is_open,
        "is_active": is_active,
        "is_visible": rws.ride.is_visible,
        "auto_approve": rws.ride.auto_approve,
        "bookings_btn": "📋 Брони",
        "complete_btn": "🏁 Завершить",
        "cancel_btn": "❌ Отменить поездку",
        "toggle_vis_btn": "👁️ Скрыть" if rws.ride.is_visible else "👁️ Показать",
        "toggle_auto_btn": "⚡ Авто-апрув: ВКЛ" if rws.ride.auto_approve else "⚡ Авто-апрув: ВЫКЛ",
        "back_btn": "⬅️ К поездкам",
    }


@inject
async def on_complete(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    rides_dao: FromDishka[RidesDAO],
):
    ride_id: int = manager.dialog_data["ride_id"]
    container = manager.middleware_data["dishka_container"]
    ride_service: RideService = await container.get(RideService)
    await ride_service.complete_ride(ride_id)
    await callback.answer("Поездка завершена", show_alert=True)
    await manager.switch_to(RidesMgmtSG.rides_list)


@inject
async def on_cancel_ride(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
):
    ride_id: int = manager.dialog_data["ride_id"]
    container = manager.middleware_data["dishka_container"]
    ride_service: RideService = await container.get(RideService)
    await ride_service.cancel_ride(ride_id)
    await callback.answer("Поездка отменена, возврат выполнен", show_alert=True)
    await manager.switch_to(RidesMgmtSG.rides_list)


@inject
async def on_toggle_visibility(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    rides_dao: FromDishka[RidesDAO],
):
    ride_id: int = manager.dialog_data["ride_id"]
    ride = await rides_dao.get_by_id(ride_id)
    if ride:
        await rides_dao.set_visibility(ride_id, not ride.is_visible)
    await manager.update({})


@inject
async def on_toggle_auto_approve(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    rides_dao: FromDishka[RidesDAO],
):
    ride_id: int = manager.dialog_data["ride_id"]
    ride = await rides_dao.get_by_id(ride_id)
    if ride:
        await rides_dao.set_auto_approve(ride_id, not ride.auto_approve)
    await manager.update({})


async def on_ride_selected(
    callback: CallbackQuery,
    select: Select,
    manager: DialogManager,
    item_id: str,
):
    manager.dialog_data["ride_id"] = int(item_id)
    await manager.next()


async def on_to_bookings(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
):
    ride_id: int = manager.dialog_data["ride_id"]
    await manager.start(RideBookingsSG.bookings_list, data={"ride_id": ride_id})


rides_management_dialog = Dialog(
    Window(
        Const("🚗 <b>Мои поездки</b>"),
        Column(
            Select(
                Format("{item[title]}"),
                id="rides_sel",
                item_id_getter=lambda item: str(item["ride_id"]),
                items="rides",
                on_click=on_ride_selected,
                when="has_rides",
            ),
        ),
        Format("{empty_text}", when="not has_rides"),
        Cancel(Format("{back_btn}")),
        state=RidesMgmtSG.rides_list,
        getter=get_rides_list,
    ),
    Window(
        Format("{ride_text}"),
        Button(Format("{bookings_btn}"), id="to_bookings", on_click=on_to_bookings),
        Group(
            Button(Format("{toggle_vis_btn}"), id="toggle_vis", on_click=on_toggle_visibility, when="is_open"),
            Button(Format("{toggle_auto_btn}"), id="toggle_auto", on_click=on_toggle_auto_approve, when="is_open"),
            width=2,
        ),
        Group(
            Button(Format("{complete_btn}"), id="complete", on_click=on_complete, when="is_active"),
            Button(Format("{cancel_btn}"), id="cancel_ride", on_click=on_cancel_ride, when="is_active"),
            width=2,
        ),
        SwitchTo(Format("{back_btn}"), id="back", state=RidesMgmtSG.rides_list),
        state=RidesMgmtSG.ride_detail,
        getter=get_ride_detail,
    ),
)
