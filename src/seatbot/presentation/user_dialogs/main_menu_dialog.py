from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import Button, Row, Start
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from seatbot.infrastructure.database.dao import BookingsDAO, UsersDAO
from seatbot.infrastructure.notifications import fmt_amount

from .states import MainMenuSG, MyBookingsSG, RequisitesSG, RidesSG, StatsSG, VipSG


@inject
async def get_main_menu(
    dialog_manager: DialogManager,
    users_dao: FromDishka[UsersDAO],
    bookings_dao: FromDishka[BookingsDAO],
    **_kwargs,
):
    user_id = dialog_manager.middleware_data["event_from_user"].id
    user = await users_dao.get_by_id(user_id)
    has_approved_booking = await bookings_dao.has_approved_for_user(user_id)
    lines = [
        "🚗 <b>SeatBot — поездки в Минск</b>\n",
    ]
    if user and user.is_vip:
        lines.append("⭐ <b>VIP:</b> поездки бесплатно, апрув автоматически.")
    if user and user.balance > 0:
        lines.append(f"💰 На депозите: <b>{fmt_amount(user.balance)} BYN</b>")
    else:
        lines[0] = lines[0].rstrip("\n")
    lines.append("\n<i><b>made by kolo</b></i>")
    return {
        "menu_text": "\n".join(lines),
        "notifications_btn": (
            "🔔 Уведомления ✅" if user and user.notify_new_rides else "🔔 Уведомления ❌"
        ),
        "has_requisites_access": has_approved_booking,
    }


@inject
async def on_toggle_notifications(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    users_dao: FromDishka[UsersDAO],
):
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
        Start(Const("⭐ VIP"), id="vip", state=VipSG.info),
        Button(Format("{notifications_btn}"), id="notifications", on_click=on_toggle_notifications),
        state=MainMenuSG.main,
        getter=get_main_menu,
    ),
)
