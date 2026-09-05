from aiogram.types import Message
from aiogram_dialog import Dialog, DialogManager, StartMode, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Cancel
from aiogram_dialog.widgets.text import Const
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from seatbot.application.services.deposit import DepositService
from seatbot.domain.exceptions import InsufficientBalanceError

from ..user_dialogs.states import DepositSG, UsersSG


def _get_user_id(manager: DialogManager) -> int | None:
    """Достаёт user_id из start_data или dialog_data."""
    start_data = manager.start_data
    if isinstance(start_data, dict) and "user_id" in start_data:
        uid = start_data["user_id"]
        manager.dialog_data["user_id"] = uid
        return uid
    return manager.dialog_data.get("user_id")


async def _parse_amount(text: str) -> float | None:
    text = text.strip().replace(",", ".")
    try:
        amount = float(text)
        if amount <= 0:
            return None
        return amount
    except ValueError:
        return None


@inject
async def on_topup_input(
    message: Message,
    widget: MessageInput,
    manager: DialogManager,
    deposit_service: FromDishka[DepositService],
):
    amount = await _parse_amount(message.text or "")
    if amount is None:
        await message.answer("❌ Введите положительное число (например, <code>50.00</code>).")
        return
    user_id = _get_user_id(manager)
    if not user_id:
        await message.answer("❌ Пользователь не определён.")
        return
    user = await deposit_service.topup(user_id, amount)
    if not user:
        await message.answer("❌ Пользователь не найден.")
        return
    await message.answer(f"✅ Депозит пополнен на {amount:.2f} BYN. Баланс: {user.balance:.2f} BYN")
    await manager.start(UsersSG.user_detail, data={"user_id": user_id}, mode=StartMode.RESET_STACK)


@inject
async def on_decrease_input(
    message: Message,
    widget: MessageInput,
    manager: DialogManager,
    deposit_service: FromDishka[DepositService],
):
    amount = await _parse_amount(message.text or "")
    if amount is None:
        await message.answer("❌ Введите положительное число (например, <code>10.00</code>).")
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
    await message.answer(f"✅ Списано {amount:.2f} BYN. Баланс: {user.balance:.2f} BYN")
    await manager.start(UsersSG.user_detail, data={"user_id": user_id}, mode=StartMode.RESET_STACK)


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
