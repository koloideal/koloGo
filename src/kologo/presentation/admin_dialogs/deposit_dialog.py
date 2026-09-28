import math

from aiogram.types import Message
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Cancel
from aiogram_dialog.widgets.text import Const
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from kologo.application.services.deposit import DepositService
from kologo.domain.exceptions import InsufficientBalanceError
from kologo.infrastructure.config import AppConfig
from kologo.infrastructure.notifications import fmt_amount

from ..user_dialogs.states import DepositSG


def _get_user_id(manager: DialogManager) -> int | None:
    start_data = manager.start_data
    if isinstance(start_data, dict) and "user_id" in start_data:
        uid = start_data["user_id"]
        manager.dialog_data["user_id"] = uid
        return uid
    return manager.dialog_data.get("user_id")


async def _parse_amount(text: str, max_amount: float) -> float | None:
    text = text.strip().replace(",", ".")
    try:
        amount = round(float(text), 2)
    except ValueError:
        return None
    if not math.isfinite(amount) or not 0 < amount <= max_amount:
        return None
    return amount


@inject
async def on_topup_input(
    message: Message,
    widget: MessageInput,
    manager: DialogManager,
    deposit_service: FromDishka[DepositService],
    app_config: FromDishka[AppConfig],
) -> None:
    amount = await _parse_amount(message.text or "", app_config.max_deposit_amount)
    if amount is None:
        await message.answer(
            f"❌ Введите число от 0.01 до {fmt_amount(app_config.max_deposit_amount)} (например, <code>50.00</code>)."
        )
        return
    user_id = _get_user_id(manager)
    if not user_id:
        await message.answer("❌ Пользователь не определён.")
        return
    user = await deposit_service.topup(user_id, amount)
    if not user:
        await message.answer("❌ Пользователь не найден.")
        return
    await message.answer(
        f"✅ Депозит пополнен на {fmt_amount(amount)} BYN. Баланс: {fmt_amount(user.balance)} BYN"
    )
    await manager.done()


@inject
async def on_decrease_input(
    message: Message,
    widget: MessageInput,
    manager: DialogManager,
    deposit_service: FromDishka[DepositService],
    app_config: FromDishka[AppConfig],
) -> None:
    amount = await _parse_amount(message.text or "", app_config.max_deposit_amount)
    if amount is None:
        await message.answer(
            f"❌ Введите число от 0.01 до {fmt_amount(app_config.max_deposit_amount)} (например, <code>10.00</code>)."
        )
        return
    user_id = _get_user_id(manager)
    if not user_id:
        await message.answer("❌ Пользователь не определён.")
        return
    try:
        user = await deposit_service.decrease(user_id, amount)
    except InsufficientBalanceError:
        await message.answer("❌ Недостаточно средств на депозите.")
        return
    if not user:
        await message.answer("❌ Пользователь не найден.")
        return
    await message.answer(f"✅ Списано {fmt_amount(amount)} BYN. Баланс: {fmt_amount(user.balance)} BYN")
    await manager.done()


deposit_dialog = Dialog(
    Window(
        Const("💰 <b>Пополнение депозита</b>\n\nВведите сумму в BYN:"),
        MessageInput(on_topup_input),
        Cancel(Const("⬅️ Отмена")),
        state=DepositSG.deposit_amount,
    ),
    Window(
        Const("💸 <b>Списание с депозита</b>\n\nВведите сумму в BYN:"),
        MessageInput(on_decrease_input),
        Cancel(Const("⬅️ Отмена")),
        state=DepositSG.decrease_amount,
    ),
)
