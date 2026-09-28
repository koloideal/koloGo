from html import escape
from typing import Any

from aiogram import F
from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Cancel, Column, Select, SwitchTo
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from kologo.infrastructure.database.dao import RequisitesDAO

from ..user_dialogs.states import AdminRequisitesSG


@inject
async def get_requisites(
    dialog_manager: DialogManager,
    requisites_dao: FromDishka[RequisitesDAO],
    **_kwargs: Any,
) -> dict[str, Any]:
    requisites = await requisites_dao.list_all()
    return {
        "has_requisites": bool(requisites),
        "requisites": [
            {"requisite_id": item.requisite_id, "title": escape(item.title)} for item in requisites
        ],
        "empty_text": "Реквизитов пока нет.",
    }


@inject
async def get_requisite_detail(
    dialog_manager: DialogManager,
    requisites_dao: FromDishka[RequisitesDAO],
    **_kwargs: Any,
) -> dict[str, Any]:
    requisite_id = dialog_manager.dialog_data.get("requisite_id", 0)
    requisite = await requisites_dao.get_by_id(requisite_id)
    if not requisite:
        return {"requisite_text": "Реквизит не найден."}
    return {"requisite_text": (f"<b>{escape(requisite.title)}</b>\n\n<code>{escape(requisite.value)}</code>")}


async def on_requisite_selected(
    callback: CallbackQuery,
    select: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    manager.dialog_data["requisite_id"] = int(item_id)
    await manager.switch_to(AdminRequisitesSG.detail)


async def on_title_input(
    message: Message,
    widget: MessageInput,
    manager: DialogManager,
) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer("Введите название реквизита.")
        return
    manager.dialog_data["requisite_title"] = title[:128]
    await manager.next()


async def on_value_input(
    message: Message,
    widget: MessageInput,
    manager: DialogManager,
) -> None:
    value = (message.text or "").strip()
    if not value:
        await message.answer("Введите значение реквизита.")
        return
    title = manager.dialog_data.get("requisite_title")
    if not title:
        await manager.switch_to(AdminRequisitesSG.title)
        return
    container = manager.middleware_data["dishka_container"]
    requisites_dao: RequisitesDAO = await container.get(RequisitesDAO)
    await requisites_dao.create(title, value)
    await message.answer("✅ Реквизит добавлен")
    await manager.switch_to(AdminRequisitesSG.list)


async def on_delete(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    requisite_id = manager.dialog_data.get("requisite_id", 0)
    container = manager.middleware_data["dishka_container"]
    requisites_dao: RequisitesDAO = await container.get(RequisitesDAO)
    deleted = await requisites_dao.delete(requisite_id)
    await callback.answer("Реквизит удалён" if deleted else "Реквизит не найден", show_alert=True)
    await manager.switch_to(AdminRequisitesSG.list)


requisites_dialog = Dialog(
    Window(
        Const("💳 <b>Реквизиты</b>"),
        Column(
            Select(
                Format("{item[title]}"),
                id="requisites",
                item_id_getter=lambda item: str(item["requisite_id"]),
                items="requisites",
                on_click=on_requisite_selected,
                when="has_requisites",
            )
        ),
        Format("{empty_text}", when=~F["has_requisites"]),
        SwitchTo(Const("➕ Добавить"), id="add", state=AdminRequisitesSG.title),
        Cancel(Const("⬅️ В панель")),
        state=AdminRequisitesSG.list,
        getter=get_requisites,
    ),
    Window(
        Const("Введите название реквизита:"),
        MessageInput(on_title_input),
        SwitchTo(Const("⬅️ Назад"), id="back", state=AdminRequisitesSG.list),
        state=AdminRequisitesSG.title,
    ),
    Window(
        Const("Введите значение реквизита:"),
        MessageInput(on_value_input),
        SwitchTo(Const("⬅️ Назад"), id="back", state=AdminRequisitesSG.title),
        state=AdminRequisitesSG.value,
    ),
    Window(
        Format("{requisite_text}"),
        Button(Const("🗑 Удалить"), id="delete", on_click=on_delete),
        SwitchTo(Const("⬅️ Назад"), id="back", state=AdminRequisitesSG.list),
        state=AdminRequisitesSG.detail,
        getter=get_requisite_detail,
    ),
)
