from aiogram.types import Message
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Cancel, SwitchTo
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from seatbot.application.services.vip import VipService
from seatbot.infrastructure.notifications import fmt_amount

from ..user_dialogs.states import AdminSettingsSG


@inject
async def get_settings_main(
    dialog_manager: DialogManager,
    vip_service: FromDishka[VipService],
    **_kwargs,
):
    price = await vip_service.get_vip_price()
    return {
        "vip_price": fmt_amount(price),
        "back_btn": "⬅️ В панель",
    }


async def on_vip_price_input(message: Message, widget: MessageInput, manager: DialogManager):
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


settings_dialog = Dialog(
    Window(
        Format("⚙️ <b>Настройки</b>\n\n⭐ Стоимость VIP: <b>{vip_price} BYN</b>"),
        SwitchTo(Const("⭐ Изменить цену VIP"), id="edit_vip_price", state=AdminSettingsSG.vip_price),
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
)
