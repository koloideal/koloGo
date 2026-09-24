from typing import Any

from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import Button, Row, Start
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from seatbot.application.services.ride import RideService
from seatbot.domain.schemas import BookingStatus, RideStatus
from seatbot.infrastructure.config import AppConfig
from seatbot.infrastructure.database.dao import BookingsDAO, RidesDAO, UsersDAO
from seatbot.infrastructure.notifications import MessageBuilder, fmt_amount, route_str

from .states import (BalanceSG, MainMenuSG, MyBookingsSG, RequisitesSG, RidesSG, StatsSG,
                     VipSG)


@inject
async def get_main_menu(
    dialog_manager: DialogManager,
    users_dao: FromDishka[UsersDAO],
    bookings_dao: FromDishka[BookingsDAO],
    ride_service: FromDishka[RideService],
    messages: FromDishka[MessageBuilder],
    app_config: FromDishka[AppConfig],
    **_kwargs: Any,
) -> dict[str, Any]:
    user_id = dialog_manager.middleware_data["event_from_user"].id
    user = await users_dao.get_by_id(user_id)
    has_approved_booking = await bookings_dao.has_approved_for_user(user_id)
    lines = ["🚗 <b>SeatBot — поездки в Минск</b>\n"]
    if user and user.is_vip:
        lines.append("⭐ <b>VIP:</b> поездки бесплатно, апрув автоматически.")
    if user and user.balance > 0:
        lines.append(f"💰 На депозите: <b>{fmt_amount(user.balance)} BYN</b>")

    next_booking = await ride_service.next_active_booking(user_id)
    next_stats = await ride_service.get_ride_stats(next_booking.ride_id) if next_booking else None
    next_ride = next_stats.ride if next_stats else None
    has_next_origin = False
    if next_booking and next_ride:
        dialog_manager.dialog_data["next_booking_id"] = next_booking.booking_id
        dialog_manager.dialog_data["next_ride_id"] = next_ride.ride_id
        status = (
            "🚙 Водитель в пути"
            if next_ride.status == RideStatus.IN_PROGRESS
            else app_config.next_booking_status.get(next_booking.status, "")
        )
        route = route_str(next_ride)
        lines += [
            "\n🗓 <b>Ваша ближайшая поездка</b>",
            f"🕒 {messages.short_date(next_ride.departure_at)}" + (f" · {route}" if route else ""),
            status,
        ]
        has_next_origin = (
            next_booking.status == BookingStatus.APPROVED
            and next_ride.origin_lat is not None
            and next_ride.origin_lon is not None
        )
    elif await ride_service.get_upcoming_rides():
        lines.append("\nАктивных броней нет — свежие поездки в разделе «🚗 Поездки».")
    elif user and user.notify_new_rides:
        lines.append("\nПоездок пока нет — сообщим, как только появятся 🔔.")
    else:
        lines.append("\nПоездок пока нет — включите 🔔 уведомления, чтобы не пропустить новые.")
    lines.append("\n<i><b>made by kolo</b></i>")
    return {
        "menu_text": "\n".join(lines),
        "notifications_btn": ("🔔 Уведомления ✅" if user and user.notify_new_rides else "🔔 Уведомления ❌"),
        "has_requisites_access": has_approved_booking,
        "has_next": next_booking is not None and next_ride is not None,
        "has_next_origin": has_next_origin,
    }


async def on_open_next_booking(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    booking_id = manager.dialog_data.get("next_booking_id")
    if booking_id:
        await manager.start(MyBookingsSG.detail, data={"booking_id": booking_id})


@inject
async def on_next_origin(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    rides_dao: FromDishka[RidesDAO],
) -> None:
    ride = await rides_dao.get_by_id(manager.dialog_data.get("next_ride_id", 0))
    if not ride or ride.origin_lat is None or ride.origin_lon is None:
        await callback.answer("Место отправления не задано", show_alert=True)
        return
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer_location(latitude=ride.origin_lat, longitude=ride.origin_lon)


@inject
async def on_toggle_notifications(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    users_dao: FromDishka[UsersDAO],
) -> None:
    user_id = manager.middleware_data["event_from_user"].id
    user = await users_dao.get_by_id(user_id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return
    enabled = not user.notify_new_rides
    await users_dao.set_notify_new_rides(user_id, enabled)
    status = "включены" if enabled else "выключены"
    await callback.answer(f"Уведомления о новых поездках {status}", show_alert=True)
    await manager.update({})


main_menu_dialog = Dialog(
    Window(
        Format("{menu_text}"),
        Row(
            Button(Const("📋 Открыть бронь"), id="next_booking", on_click=on_open_next_booking),
            Button(
                Const("📍 Где садиться"), id="next_origin", on_click=on_next_origin, when="has_next_origin"
            ),
            when="has_next",
        ),
        Row(
            Start(Const("🚗 Поездки"), id="rides", state=RidesSG.list),
            Start(Const("📋 Мои брони"), id="mybookings", state=MyBookingsSG.list),
        ),
        Row(
            Start(Const("📊 Статистика"), id="stats", state=StatsSG.stats),
            Start(
                Const("💳 Реквизиты"),
                id="requisites",
                state=RequisitesSG.list,
                when="has_requisites_access",
            ),
        ),
        Row(
            Start(Const("⭐ VIP"), id="vip", state=VipSG.info),
            Start(Const("💰 Баланс"), id="balance", state=BalanceSG.balance),
        ),
        Button(Format("{notifications_btn}"), id="notifications", on_click=on_toggle_notifications),
        state=MainMenuSG.main,
        getter=get_main_menu,
    ),
)
