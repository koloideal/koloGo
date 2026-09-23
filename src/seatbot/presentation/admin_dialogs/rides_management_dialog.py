from typing import Any

from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import (Button, Cancel, Group, ScrollingGroup, Select,
                                        SwitchTo, Url)
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from seatbot.application.services.ride import RideService
from seatbot.application.services.tracking import TrackingService
from seatbot.domain.schemas import RideStatus
from seatbot.infrastructure.database.dao import RidesDAO, TrackPointsDAO
from seatbot.infrastructure.geo import GeoService
from seatbot.infrastructure.notifications import MessageBuilder, fmt_amount, route_str
from seatbot.infrastructure.time import LocalClock

from ..user_dialogs.states import RideBookingsSG, RidesMgmtSG

_STATUS_EMOJI = {
    RideStatus.OPEN: "🟢",
    RideStatus.CLOSED: "🟡",
    RideStatus.IN_PROGRESS: "🚙",
    RideStatus.COMPLETED: "✅",
    RideStatus.CANCELLED: "❌",
}


@inject
async def get_rides_list(
    dialog_manager: DialogManager,
    rides_dao: FromDishka[RidesDAO],
    clock: FromDishka[LocalClock],
    **_kwargs: Any,
) -> dict[str, Any]:
    rides = await rides_dao.list_all(limit=100)
    if not rides:
        return {"has_rides": False, "empty_text": "🚫 Поездок пока нет.", "back_btn": "⬅️ В панель"}
    items = []
    for rws in rides:
        emoji = _STATUS_EMOJI.get(rws.ride.status, "•")
        price_str = "бесплатно" if rws.ride.is_free else f"{fmt_amount(rws.ride.price)} BYN"
        route = route_str(rws.ride)
        route_part = f" • {route}" if route else ""
        if rws.ride.status == RideStatus.COMPLETED:
            seats_str = f"{rws.finished_seats}/{rws.ride.seats_total} ехало"
        elif rws.ride.status == RideStatus.CANCELLED:
            seats_str = f"{rws.ride.seats_total} мест"
        else:
            seats_str = f"{rws.free_seats}/{rws.ride.seats_total} мест"
        items.append(
            {
                "ride_id": rws.ride.ride_id,
                "title": (
                    f"{emoji} {clock.fmt(rws.ride.started_at or rws.ride.departure_at, '%d.%m %H:%M')} • "
                    f"{price_str} • {seats_str}{route_part}"
                ),
            }
        )
    return {"has_rides": True, "rides": items, "back_btn": "⬅️ В панель"}


@inject
async def get_ride_detail(
    dialog_manager: DialogManager,
    rides_dao: FromDishka[RidesDAO],
    track_dao: FromDishka[TrackPointsDAO],
    messages: FromDishka[MessageBuilder],
    geo: FromDishka[GeoService],
    **_kwargs: Any,
) -> dict[str, Any]:
    if "ride_id" not in dialog_manager.dialog_data:
        start_data = dialog_manager.start_data
        if isinstance(start_data, dict):
            dialog_manager.dialog_data["ride_id"] = start_data["ride_id"]
    ride_id: int = dialog_manager.dialog_data["ride_id"]
    rws = await rides_dao.get_with_stats(ride_id)
    if not rws:
        return {"ride_text": "🚫 Поездка не найдена", "back_btn": "⬅️ Назад"}
    is_open = rws.ride.status == RideStatus.OPEN
    is_active = rws.ride.status in (RideStatus.OPEN, RideStatus.CLOSED)
    can_finish = rws.ride.status in (RideStatus.OPEN, RideStatus.CLOSED, RideStatus.IN_PROGRESS)
    track_points = await track_dao.list_for_ride(ride_id)
    has_track = len(track_points) >= 2
    route_url = geo.yandex_route_url(track_points) if has_track else ""
    return {
        "ride_text": messages.ride_card(rws),
        "ride_id": ride_id,
        "is_open": is_open,
        "is_active": is_active,
        "can_finish": can_finish,
        "is_visible": rws.ride.is_visible,
        "auto_approve": rws.ride.auto_approve,
        "has_track": has_track,
        "route_url": route_url,
        "bookings_btn": "📋 Брони",
        "change_time_btn": "🕒 Изменить время",
        "start_btn": "🚀 Старт поездки",
        "complete_btn": "🏁 Завершить",
        "cancel_btn": "❌ Отменить",
        "route_btn": "🗺 Маршрут (Яндекс)",
        "toggle_vis_btn": "👁️ Скрыть" if rws.ride.is_visible else "👁️ Показать",
        "toggle_auto_btn": "⚡ Авто-апрув ✅" if rws.ride.auto_approve else "⚡ Авто-апрув ❌",
        "back_btn": "⬅️ К поездкам",
    }


@inject
async def on_complete(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    rides_dao: FromDishka[RidesDAO],
) -> None:
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
) -> None:
    ride_id: int = manager.dialog_data["ride_id"]
    container = manager.middleware_data["dishka_container"]
    ride_service: RideService = await container.get(RideService)
    await ride_service.cancel_ride(ride_id)
    await callback.answer("Поездка отменена, пассажиры уведомлены", show_alert=True)
    await manager.switch_to(RidesMgmtSG.rides_list)


@inject
async def on_toggle_visibility(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    rides_dao: FromDishka[RidesDAO],
) -> None:
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
) -> None:
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
) -> None:
    manager.dialog_data["ride_id"] = int(item_id)
    await manager.next()


async def on_to_bookings(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    ride_id: int = manager.dialog_data["ride_id"]
    await manager.start(RideBookingsSG.bookings_list, data={"ride_id": ride_id})


@inject
async def on_start_ride(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    tracking_service: FromDishka[TrackingService],
) -> None:
    ride_id: int = manager.dialog_data["ride_id"]
    ride = await tracking_service.request_start(ride_id)
    if not ride:
        await callback.answer("Поездку нельзя стартовать (неверный статус)", show_alert=True)
        return
    await callback.answer(
        "📍 Отправьте боту live-геолокацию (📎 → Геопозиция → Транслировать геопозицию)",
        show_alert=True,
    )
    if callback.message:
        await callback.message.answer(
            "🚀 <b>Ожидаю live-геолокацию для поездки "
            f"#{ride_id}.</b>\n\n"
            "Отправьте live-гео (📎 → Геопозиция → «Транслировать геопозицию») — "
            "трекинг начнётся автоматически."
        )


async def on_change_time(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    await manager.switch_to(RidesMgmtSG.change_time)


@inject
async def on_time_input(
    message: Message,
    widget: MessageInput,
    manager: DialogManager,
    rides_dao: FromDishka[RidesDAO],
    clock: FromDishka[LocalClock],
) -> None:
    text = (message.text or "").strip()
    try:
        parts = text.replace(".", ":").split(":")
        if len(parts) != 2:
            raise ValueError
        hour = int(parts[0])
        minute = int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите время в формате ЧЧ:ММ (например, <code>18:30</code>).")
        return
    ride_id: int = manager.dialog_data["ride_id"]
    ride = await rides_dao.get_by_id(ride_id)
    if not ride:
        await message.answer("❌ Поездка не найдена.")
        return
    container = manager.middleware_data["dishka_container"]
    ride_service: RideService = await container.get(RideService)
    updated = await ride_service.change_ride_time(ride_id, hour, minute)
    if not updated:
        await message.answer("❌ Не удалось изменить время. Поездка уже завершена или отменена.")
        return
    await message.answer(
        f"✅ Время изменено на <b>{clock.fmt(updated.departure_at, '%H:%M')}</b>. Пассажиры уведомлены."
    )
    await manager.switch_to(RidesMgmtSG.ride_detail)


rides_management_dialog = Dialog(
    Window(
        Const("🚗 <b>Мои поездки</b>"),
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
        Cancel(Format("{back_btn}")),
        state=RidesMgmtSG.rides_list,
        getter=get_rides_list,
    ),
    Window(
        Format("{ride_text}"),
        Button(Format("{bookings_btn}"), id="to_bookings", on_click=on_to_bookings),
        Button(Format("{change_time_btn}"), id="change_time", on_click=on_change_time, when="is_active"),
        Button(Format("{start_btn}"), id="start_ride", on_click=on_start_ride, when="is_active"),
        Group(
            Button(
                Format("{toggle_vis_btn}"), id="toggle_vis", on_click=on_toggle_visibility, when="is_open"
            ),
            Button(
                Format("{toggle_auto_btn}"), id="toggle_auto", on_click=on_toggle_auto_approve, when="is_open"
            ),
            width=2,
        ),
        Group(
            SwitchTo(
                Format("{complete_btn}"), id="complete", state=RidesMgmtSG.complete_confirm, when="can_finish"
            ),
            Button(Format("{cancel_btn}"), id="cancel_ride", on_click=on_cancel_ride, when="can_finish"),
            width=2,
        ),
        Url(Format("{route_btn}"), url=Format("{route_url}"), when="has_track"),
        SwitchTo(Format("{back_btn}"), id="back", state=RidesMgmtSG.rides_list),
        state=RidesMgmtSG.ride_detail,
        getter=get_ride_detail,
    ),
    Window(
        Format("{ride_text}"),
        Const("\n🏁 <b>Завершить эту поездку?</b>\n\nВсе одобренные брони будут завершены."),
        Button(Const("✅ Да, завершить"), id="confirm_complete", on_click=on_complete),
        SwitchTo(Const("⬅️ Отмена"), id="back", state=RidesMgmtSG.ride_detail),
        state=RidesMgmtSG.complete_confirm,
        getter=get_ride_detail,
    ),
    Window(
        Const(
            "🕒 <b>Изменение времени поездки</b>\n\n"
            "Введите новое время в формате <code>ЧЧ:ММ</code>.\n"
            "Например: <code>18:30</code>\n\n"
            "Дата останется прежней. Пассажиры будут уведомлены."
        ),
        MessageInput(on_time_input),
        SwitchTo(Const("⬅️ Назад"), id="back", state=RidesMgmtSG.ride_detail),
        state=RidesMgmtSG.change_time,
    ),
)
