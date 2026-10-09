from typing import Any

from aiogram import F
from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import (Button, Cancel, ScrollingGroup, Select, SwitchTo,
                                        Url)
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from kologo.application.services.ride import RideService
from kologo.domain.schemas import BookingStatus
from kologo.infrastructure.config import AppConfig
from kologo.infrastructure.database.dao import (BookingsDAO, RidesDAO, TrackPointsDAO,
                                                UsersDAO)
from kologo.infrastructure.geo import GeoService
from kologo.infrastructure.notifications import MessageBuilder, fmt_amount
from kologo.infrastructure.time import LocalClock

from .states import MyBookingsSG


@inject
async def get_my_bookings(
    dialog_manager: DialogManager,
    bookings_dao: FromDishka[BookingsDAO],
    rides_dao: FromDishka[RidesDAO],
    users_dao: FromDishka[UsersDAO],
    messages: FromDishka[MessageBuilder],
    clock: FromDishka[LocalClock],
    app_config: FromDishka[AppConfig],
    **_kwargs: Any,
) -> dict[str, Any]:
    user_id = dialog_manager.middleware_data["event_from_user"].id
    user = await users_dao.get_by_id(user_id)
    is_vip = bool(user and user.is_vip)
    bookings = await bookings_dao.list_for_user(user_id, limit=100)
    if not bookings:
        return {
            "has_bookings": False,
            "empty_text": "🚫 У вас пока нет броней.\n\nСвободные места — в разделе «🚗 Поездки».",
            "back_btn": "⬅️ В меню",
        }
    items = []
    for b in bookings:
        ride = await rides_dao.get_by_id(b.ride_id)
        if not ride:
            continue
        emoji = app_config.booking_status_emoji.get(b.status, "•")
        pay = messages.payment_short(b.paid_amount, float(ride.price), ride.is_free or is_vip)
        items.append(
            {
                "booking_id": b.booking_id,
                "title": (
                    f"{emoji} {clock.fmt(ride.started_at or ride.departure_at, '%d.%m %H:%M')} • {pay}"
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
    users_dao: FromDishka[UsersDAO],
    track_dao: FromDishka[TrackPointsDAO],
    geo: FromDishka[GeoService],
    messages: FromDishka[MessageBuilder],
    ride_service: FromDishka[RideService],
    **_kwargs: Any,
) -> dict[str, Any]:
    booking_id: int = dialog_manager.dialog_data["booking_id"]
    booking = await bookings_dao.get_by_id(booking_id)
    if not booking:
        return {"booking_text": "🚫 Бронь не найдена", "back_btn": "⬅️ Назад"}
    ride = await rides_dao.get_by_id(booking.ride_id)
    if not ride:
        return {"booking_text": "🚫 Поездка не найдена", "back_btn": "⬅️ Назад"}
    user = await users_dao.get_by_id(booking.user_id)
    can_cancel = ride_service.can_user_cancel(booking, ride)
    has_origin_geo = (
        booking.status == BookingStatus.APPROVED
        and ride.origin_lat is not None
        and ride.origin_lon is not None
    )
    route_url = None
    if booking.status == BookingStatus.COMPLETED:
        points = await track_dao.list_for_ride(ride.ride_id)
        if len(points) >= 2:
            route_url = geo.yandex_route_url(points)
    text = messages.booking_card(booking, ride, is_vip=bool(user and user.is_vip))
    if booking.status == BookingStatus.PENDING:
        text += (
            "\n\n⏳ Заявка ждёт решения водителя — ответ придёт сообщением. "
            "Если место не достанется, заявка отклонится автоматически."
        )
    return {
        "booking_text": text,
        "can_cancel": can_cancel,
        "has_origin_geo": has_origin_geo,
        "route_url": route_url,
        "cancel_btn": "🚫 Отменить бронь",
        "origin_btn": "📍 Место отправления",
        "route_btn": "🗺 Маршрут на карте",
        "back_btn": "⬅️ К броням",
    }


@inject
async def on_show_origin(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    bookings_dao: FromDishka[BookingsDAO],
    rides_dao: FromDishka[RidesDAO],
) -> None:
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
) -> None:
    booking_id: int = manager.dialog_data["booking_id"]
    user_id = manager.middleware_data["event_from_user"].id
    booking = await ride_service.cancel_booking_by_user(booking_id, user_id)
    if not booking:
        await callback.answer(
            "Не удалось отменить бронь: поездка уже отправилась или бронь не активна.", show_alert=True
        )
    elif booking.paid_amount > 0:
        await callback.answer(
            f"Бронь отменена, {fmt_amount(booking.paid_amount)} BYN возвращено на депозит.", show_alert=True
        )
    else:
        await callback.answer("Бронь отменена.", show_alert=True)
    await manager.switch_to(MyBookingsSG.list)


async def on_my_bookings_start(start_data: Any, manager: DialogManager) -> None:
    if isinstance(start_data, dict) and "booking_id" in start_data:
        manager.dialog_data["booking_id"] = start_data["booking_id"]


async def on_booking_selected(
    callback: CallbackQuery,
    select: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
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
        Format("{empty_text}", when=~F["has_bookings"]),
        Cancel(Format("{back_btn}")),
        state=MyBookingsSG.list,
        getter=get_my_bookings,
    ),
    Window(
        Format("{booking_text}"),
        Button(Format("{cancel_btn}"), id="cancel_booking", on_click=on_cancel_booking, when="can_cancel"),
        Button(Format("{origin_btn}"), id="show_origin", on_click=on_show_origin, when="has_origin_geo"),
        Url(Format("{route_btn}"), Format("{route_url}"), when="route_url"),
        SwitchTo(Format("{back_btn}"), id="back", state=MyBookingsSG.list),
        state=MyBookingsSG.detail,
        getter=get_booking_detail,
    ),
    on_start=on_my_bookings_start,
)
