from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import (Button, Cancel, Group, ScrollingGroup, Select,
                                        SwitchTo)
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from seatbot.application.services.statistics import StatisticsService
from seatbot.application.services.user import UserService
from seatbot.infrastructure.config.models import Config
from seatbot.infrastructure.database.dao import UsersDAO
from seatbot.infrastructure.notifications import fmt_amount, user_display

from ..user_dialogs.states import DepositSG, UsersSG


@inject
async def get_users_list(
    dialog_manager: DialogManager,
    statistics_service: FromDishka[StatisticsService],
    config: FromDishka[Config],
    **_kwargs,
):
    stats = await statistics_service.all_users_stats(limit=100, exclude_user_id=config.bot.creator_id)
    if not stats:
        return {"has_users": False, "empty_text": "🚫 Нет пользователей.", "back_btn": "⬅️ В панель"}
    items = []
    for s in stats:
        badges = []
        if s.is_vip:
            badges.append("⭐")
        if s.is_banned:
            badges.append("🚫")
        badge_str = " " + "".join(badges) if badges else ""
        uname = user_display(s.username, s.first_name, s.user_id)
        items.append(
            {
                "user_id": s.user_id,
                "title": f"{uname}{badge_str} • {s.total_rides} поездок • {fmt_amount(s.balance)} BYN",
            }
        )
    return {"has_users": True, "users": items, "back_btn": "⬅️ В панель"}


@inject
async def get_user_detail(
    dialog_manager: DialogManager,
    statistics_service: FromDishka[StatisticsService],
    users_dao: FromDishka[UsersDAO],
    **_kwargs,
):
    if "user_id" not in dialog_manager.dialog_data:
        start_data = dialog_manager.start_data
        if isinstance(start_data, dict) and "user_id" in start_data:
            dialog_manager.dialog_data["user_id"] = start_data["user_id"]
    user_id: int = dialog_manager.dialog_data.get("user_id", 0)
    if not user_id:
        return {"user_text": "🚫 Пользователь не найден", "back_btn": "⬅️ Назад"}
    stats = await statistics_service.user_stats(user_id)
    user = await users_dao.get_by_id(user_id)
    if not stats or not user:
        return {"user_text": "🚫 Пользователь не найден", "back_btn": "⬅️ Назад"}
    last_ride = stats.last_ride_at.strftime("%d.%m.%Y") if stats.last_ride_at else "—"
    uname = user_display(user.username, user.first_name, user.user_id)
    text = (
        f"<b>👤 Клиент</b>\n\n"
        f"ID: <code>{user.user_id}</code>\n"
        f"Имя: {uname}\n"
        f"💳 Депозит: <b>{fmt_amount(user.balance)} BYN</b>\n"
        f"🚗 Поездок завершено: <b>{stats.total_rides}</b>\n"
        f"💰 Всего потрачено: <b>{fmt_amount(stats.total_spent)} BYN</b>\n"
        f"📅 Последняя бронь: {last_ride}\n"
        f"⭐ VIP: {'да' if user.is_vip else 'нет'}\n"
        f"🚫 В ЧС: {'да' if user.is_banned else 'нет'}"
    )
    return {
        "user_text": text,
        "is_banned": user.is_banned,
        "is_vip": user.is_vip,
        "ban_btn": "🚫 В ЧС" if not user.is_banned else "✅ Из ЧС",
        "vip_btn": "⭐ Выдать VIP" if not user.is_vip else "⭐ Снять VIP",
        "deposit_btn": "💰 Пополнить депозит",
        "decrease_btn": "💸 Списать депозит",
        "back_btn": "⬅️ К клиентам",
    }


@inject
async def on_toggle_ban(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    user_service: FromDishka[UserService],
):
    user_id: int = manager.dialog_data["user_id"]
    user = await user_service.is_banned(user_id)
    if user:
        await user_service.set_unbanned(user_id)
        await callback.answer("Удалён из ЧС", show_alert=True)
    else:
        await user_service.set_banned(user_id)
        await callback.answer("Добавлен в ЧС", show_alert=True)
    await manager.update({})


@inject
async def on_toggle_vip(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    user_service: FromDishka[UserService],
):
    user_id: int = manager.dialog_data["user_id"]
    is_vip = await user_service.is_vip(user_id)
    await user_service.set_vip(user_id, not is_vip)
    await callback.answer("VIP изменён", show_alert=True)
    await manager.update({})


async def on_deposit_click(callback: CallbackQuery, button: Button, manager: DialogManager):
    user_id: int = manager.dialog_data["user_id"]
    await manager.start(DepositSG.deposit_amount, data={"user_id": user_id})


async def on_decrease_click(callback: CallbackQuery, button: Button, manager: DialogManager):
    user_id: int = manager.dialog_data["user_id"]
    await manager.start(DepositSG.decrease_amount, data={"user_id": user_id})


async def on_user_selected(
    callback: CallbackQuery,
    select: Select,
    manager: DialogManager,
    item_id: str,
):
    manager.dialog_data["user_id"] = int(item_id)
    await manager.next()


users_dialog = Dialog(
    Window(
        Const("👥 <b>Клиенты</b>"),
        ScrollingGroup(
            Select(
                Format("{item[title]}"),
                id="users_sel",
                item_id_getter=lambda item: str(item["user_id"]),
                items="users",
                on_click=on_user_selected,
                when="has_users",
            ),
            width=1,
            height=8,
            id="users_scroll",
        ),
        Format("{empty_text}", when="not has_users"),
        Cancel(Format("{back_btn}")),
        state=UsersSG.users_list,
        getter=get_users_list,
    ),
    Window(
        Format("{user_text}"),
        Group(
            Button(Format("{deposit_btn}"), id="deposit", on_click=on_deposit_click),
            Button(Format("{decrease_btn}"), id="decrease", on_click=on_decrease_click),
            width=2,
        ),
        Group(
            Button(Format("{ban_btn}"), id="toggle_ban", on_click=on_toggle_ban),
            Button(Format("{vip_btn}"), id="toggle_vip", on_click=on_toggle_vip),
            width=2,
        ),
        SwitchTo(Format("{back_btn}"), id="back", state=UsersSG.users_list),
        state=UsersSG.user_detail,
        getter=get_user_detail,
    ),
)
