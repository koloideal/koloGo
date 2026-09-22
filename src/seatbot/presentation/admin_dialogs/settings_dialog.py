from html import escape
from typing import Any

from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Cancel, ScrollingGroup, Select, SwitchTo
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from seatbot.application.services.payment import PaymentService
from seatbot.application.services.vip import VipService
from seatbot.infrastructure.database.dao import LocationsDAO
from seatbot.infrastructure.notifications import fmt_amount

from ..user_dialogs.states import AdminSettingsSG


@inject
async def get_locations_list(
    dialog_manager: DialogManager,
    locations_dao: FromDishka[LocationsDAO],
    **_kwargs: Any,
) -> dict[str, Any]:
    locations = await locations_dao.list_all()
    items = [{"location_id": loc.location_id, "title": f"🗑 {loc.name}"} for loc in locations]
    return {
        "has_locations": bool(items),
        "locations": items,
        "empty_text": "📍 Точек пока нет. Добавьте первую.",
        "back_btn": "⬅️ К настройкам",
    }


async def on_add_location(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    await manager.switch_to(AdminSettingsSG.location_name)


async def on_location_selected(
    callback: CallbackQuery,
    select: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    manager.dialog_data["location_id"] = int(item_id)
    await manager.switch_to(AdminSettingsSG.location_delete)


@inject
async def get_location_delete(
    dialog_manager: DialogManager,
    locations_dao: FromDishka[LocationsDAO],
    **_kwargs: Any,
) -> dict[str, Any]:
    location_id = dialog_manager.dialog_data.get("location_id")
    loc = await locations_dao.get_by_id(location_id) if location_id is not None else None
    if not loc:
        return {"location_text": "🚫 Точка не найдена.", "back_btn": "⬅️ К точкам"}
    return {
        "location_text": f"🗑 <b>Удалить точку «{escape(loc.name)}»?</b>",
        "back_btn": "⬅️ К точкам",
    }


@inject
async def on_confirm_delete_location(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    locations_dao: FromDishka[LocationsDAO],
) -> None:
    location_id = manager.dialog_data.get("location_id")
    if location_id is not None:
        await locations_dao.delete(int(location_id))
    await callback.answer("🗑 Точка удалена", show_alert=True)
    await manager.switch_to(AdminSettingsSG.locations)


async def on_location_name_input(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    name = (message.text or "").strip()[:128]
    if not name:
        await message.answer("❌ Введите название точки.")
        return
    manager.dialog_data["location_name"] = name
    await manager.next()


async def on_location_geo_input(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    if not message.location:
        await message.answer("❌ Отправьте геолокацию точки (📎 → Геопозиция).")
        return
    container = manager.middleware_data["dishka_container"]
    locations_dao: LocationsDAO = await container.get(LocationsDAO)
    name = manager.dialog_data["location_name"]
    await locations_dao.create(name, message.location.latitude, message.location.longitude)
    await message.answer(f"✅ Точка «{name}» сохранена.")
    await manager.switch_to(AdminSettingsSG.locations)


async def on_location_wrong_input(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    await message.answer("❌ Отправьте геолокацию точки (📎 → Геопозиция).")


@inject
async def get_settings_main(
    dialog_manager: DialogManager,
    vip_service: FromDishka[VipService],
    payment_service: FromDishka[PaymentService],
    **_kwargs: Any,
) -> dict[str, Any]:
    price = await vip_service.get_vip_price()
    rate = await payment_service.get_byn_to_usd_rate()
    stars_rate = await payment_service.get_byn_to_stars_rate()
    return {
        "vip_price": fmt_amount(price),
        "byn_to_usd_rate": fmt_amount(rate),
        "byn_to_stars_rate": fmt_amount(stars_rate),
        "back_btn": "⬅️ В панель",
    }


async def on_vip_price_input(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    text = (message.text or "").strip().replace(",", ".")
    try:
        price = float(text)
        if price < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите неотрицательное число (например, <code>100</code>).")
        return
    container = manager.middleware_data["dishka_container"]
    vip_service: VipService = await container.get(VipService)
    await vip_service.set_vip_price(price)
    await message.answer(f"✅ Стоимость VIP обновлена: <b>{fmt_amount(price)} BYN</b>")
    await manager.switch_to(AdminSettingsSG.main)


async def on_exchange_rate_input(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    text = (message.text or "").strip().replace(",", ".")
    try:
        rate = float(text)
        if rate <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительное число (например, <code>3.2</code>).")
        return
    container = manager.middleware_data["dishka_container"]
    payment_service: PaymentService = await container.get(PaymentService)
    await payment_service.set_byn_to_usd_rate(rate)
    await message.answer(f"✅ Курс BYN→USD обновлён: <b>1 USD = {fmt_amount(rate)} BYN</b>")
    await manager.switch_to(AdminSettingsSG.main)


async def on_stars_rate_input(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    text = (message.text or "").strip().replace(",", ".")
    try:
        rate = float(text)
        if rate <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительное число (например, <code>1.0</code>).")
        return
    container = manager.middleware_data["dishka_container"]
    payment_service: PaymentService = await container.get(PaymentService)
    await payment_service.set_byn_to_stars_rate(rate)
    await message.answer(f"✅ Курс BYN→Stars обновлён: <b>1 ⭐ = {fmt_amount(rate)} BYN</b>")
    await manager.switch_to(AdminSettingsSG.main)


settings_dialog = Dialog(
    Window(
        Format(
            "⚙️ <b>Настройки</b>\n\n"
            "⭐ Стоимость VIP: <b>{vip_price} BYN</b>\n"
            "💱 Курс BYN→USD: <b>1 USD = {byn_to_usd_rate} BYN</b>\n"
            "🌟 Курс BYN→Stars: <b>1 ⭐ = {byn_to_stars_rate} BYN</b>"
        ),
        SwitchTo(Const("⭐ Изменить цену VIP"), id="edit_vip_price", state=AdminSettingsSG.vip_price),
        SwitchTo(
            Const("💱 Изменить курс BYN→USD"),
            id="edit_rate",
            state=AdminSettingsSG.byn_rate,
        ),
        SwitchTo(
            Const("🌟 Изменить курс BYN→Stars"),
            id="edit_stars_rate",
            state=AdminSettingsSG.stars_rate,
        ),
        SwitchTo(
            Const("📍 Точки маршрута"),
            id="locations",
            state=AdminSettingsSG.locations,
        ),
        Cancel(Format("{back_btn}")),
        state=AdminSettingsSG.main,
        getter=get_settings_main,
    ),
    Window(
        Const("⭐ <b>Новая стоимость VIP</b>\n\nВведите цену в BYN (например, <code>100</code>):"),
        MessageInput(on_vip_price_input),
        SwitchTo(Const("⬅️ Назад"), id="back", state=AdminSettingsSG.main),
        state=AdminSettingsSG.vip_price,
    ),
    Window(
        Const(
            "💱 <b>Курс BYN→USD</b>\n\n"
            "Сколько BYN за 1 USD (например, <code>3.2</code>).\n"
            "По этому курсу сумма в BYN конвертируется в USDT при пополнении."
        ),
        MessageInput(on_exchange_rate_input),
        SwitchTo(Const("⬅️ Назад"), id="back", state=AdminSettingsSG.main),
        state=AdminSettingsSG.byn_rate,
    ),
    Window(
        Const(
            "🌟 <b>Курс BYN→Stars</b>\n\n"
            "Сколько BYN за 1 звезду (например, <code>1.0</code>).\n"
            "По этому курсу сумма в BYN конвертируется в Telegram Stars."
        ),
        MessageInput(on_stars_rate_input),
        SwitchTo(Const("⬅️ Назад"), id="back", state=AdminSettingsSG.main),
        state=AdminSettingsSG.stars_rate,
    ),
    Window(
        Const("📍 <b>Точки маршрута</b>\n\nНажмите на точку, чтобы удалить её."),
        ScrollingGroup(
            Select(
                Format("{item[title]}"),
                id="loc_sel",
                item_id_getter=lambda item: str(item["location_id"]),
                items="locations",
                on_click=on_location_selected,
                when="has_locations",
            ),
            width=1,
            height=8,
            id="loc_scroll",
        ),
        Format("{empty_text}", when="not has_locations"),
        Button(Const("➕ Добавить точку"), id="add_loc", on_click=on_add_location),
        SwitchTo(Format("{back_btn}"), id="back", state=AdminSettingsSG.main),
        state=AdminSettingsSG.locations,
        getter=get_locations_list,
    ),
    Window(
        Format("{location_text}"),
        Button(
            Const("🗑 Да, удалить"),
            id="confirm_del_loc",
            on_click=on_confirm_delete_location,
        ),
        SwitchTo(Format("{back_btn}"), id="back", state=AdminSettingsSG.locations),
        state=AdminSettingsSG.location_delete,
        getter=get_location_delete,
    ),
    Window(
        Const("📍 <b>Новая точка</b>\n\nВведите название (например, <code>Колледж</code>):"),
        MessageInput(on_location_name_input),
        SwitchTo(Const("⬅️ Назад"), id="back", state=AdminSettingsSG.locations),
        state=AdminSettingsSG.location_name,
    ),
    Window(
        Const("📍 <b>Геопозиция точки</b>\n\nОтправьте геолокацию этой точки (📎 → Геопозиция)."),
        MessageInput(on_location_geo_input, content_types=["location"]),
        MessageInput(on_location_wrong_input, content_types=["text"]),
        SwitchTo(Const("⬅️ Назад"), id="back", state=AdminSettingsSG.locations),
        state=AdminSettingsSG.location_geo,
    ),
)
