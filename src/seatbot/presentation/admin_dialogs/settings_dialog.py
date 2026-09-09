from aiogram.types import Message
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Cancel, SwitchTo
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from seatbot.application.services.payment import PaymentService
from seatbot.application.services.vip import VipService
from seatbot.infrastructure.notifications import fmt_amount

from ..user_dialogs.states import AdminSettingsSG


@inject
async def get_settings_main(
    dialog_manager: DialogManager,
    vip_service: FromDishka[VipService],
    payment_service: FromDishka[PaymentService],
    **_kwargs,
):
    price = await vip_service.get_vip_price()
    rate = await payment_service.get_byn_to_usd_rate()
    stars_rate = await payment_service.get_byn_to_stars_rate()
    return {
        "vip_price": fmt_amount(price),
        "byn_to_usd_rate": fmt_amount(rate),
        "byn_to_stars_rate": fmt_amount(stars_rate),
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


async def on_exchange_rate_input(message: Message, widget: MessageInput, manager: DialogManager):
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


async def on_stars_rate_input(message: Message, widget: MessageInput, manager: DialogManager):
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
)
