from typing import Any

from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, StartMode, Window
from aiogram_dialog.widgets.kbd import Button, Cancel
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from kologo.application.services.vip import VipService
from kologo.domain.exceptions import InsufficientBalanceError
from kologo.infrastructure.database.dao import UsersDAO
from kologo.infrastructure.notifications import MessageBuilder

from .states import MainMenuSG, VipSG


@inject
async def get_vip_info(
    dialog_manager: DialogManager,
    users_dao: FromDishka[UsersDAO],
    vip_service: FromDishka[VipService],
    messages: FromDishka[MessageBuilder],
    **_kwargs: Any,
) -> dict[str, Any]:
    user_id = dialog_manager.middleware_data["event_from_user"].id
    user = await users_dao.get_by_id(user_id)
    if not user:
        return {"vip_text": "Сначала нажмите /start", "can_buy": False, "is_vip": False}
    price = await vip_service.get_vip_price()
    text = messages.vip_info_text(price, user.is_vip, user.balance)
    return {
        "vip_text": text,
        "can_buy": not user.is_vip and user.balance >= price,
        "is_vip": user.is_vip,
    }


@inject
async def on_buy_vip(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    users_dao: FromDishka[UsersDAO],
    vip_service: FromDishka[VipService],
) -> None:
    user_id = manager.middleware_data["event_from_user"].id
    user = await users_dao.get_by_id(user_id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return
    if user.is_vip:
        await callback.answer("Вы уже VIP!", show_alert=True)
        return
    try:
        await vip_service.purchase_vip(user)
    except InsufficientBalanceError:
        await callback.answer("Недостаточно средств на депозите", show_alert=True)
        return
    await callback.answer("⭐ VIP-статус активирован!", show_alert=True)
    await manager.start(MainMenuSG.main, mode=StartMode.RESET_STACK)


vip_dialog = Dialog(
    Window(
        Format("{vip_text}"),
        Button(Const("⭐ Купить VIP"), id="buy_vip", on_click=on_buy_vip, when="can_buy"),
        Cancel(Const("⬅️ Назад")),
        state=VipSG.info,
        getter=get_vip_info,
    ),
)
