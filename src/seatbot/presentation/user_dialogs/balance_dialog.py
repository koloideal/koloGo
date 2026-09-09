from aiogram import Bot
from aiogram.types import CallbackQuery, LabeledPrice, Message
from aiogram_dialog import Dialog, DialogManager, StartMode, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Cancel, Row, SwitchTo, Url
from aiogram_dialog.widgets.text import Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from seatbot.application.services.payment import PaymentService
from seatbot.domain.schemas import TransactionStatus
from seatbot.infrastructure.database.dao import TransactionsDAO, UsersDAO
from seatbot.infrastructure.notifications import MessageBuilder, fmt_amount

from .states import BalanceSG, MainMenuSG


@inject
async def get_balance_data(
    dialog_manager: DialogManager,
    users_dao: FromDishka[UsersDAO],
    messages: FromDishka[MessageBuilder],
    **_kwargs,
):
    user_id = dialog_manager.middleware_data["event_from_user"].id
    user = await users_dao.get_by_id(user_id)
    if not user:
        return {"balance_text": "Сначала нажмите /start", "top_up_btn": "💳 Пополнить", "back_btn": "⬅️ Назад"}
    return {
        "balance_text": messages.balance_info_text(user.balance, user.is_vip),
        "top_up_btn": "💳 Пополнить",
        "back_btn": "⬅️ Назад",
    }


async def get_top_up_amount_data(**_kwargs):
    return {
        "amount_prompt": (
            "💳 <b>Пополнение баланса</b>\n\n"
            "Введите сумму в BYN (от 1 до 1000):\n"
            "Пример: <code>50</code>"
        ),
        "back_btn": "⬅️ Назад",
    }


async def get_top_up_method_data(**_kwargs):
    return {
        "method_prompt": "💳 <b>Выберите способ оплаты</b>",
        "cryptobot_btn": "🤖 CryptoBot (USDT)",
        "stars_btn": "⭐ Telegram Stars",
        "back_btn": "⬅️ Назад",
    }


@inject
async def get_invoice_data(
    dialog_manager: DialogManager,
    transactions_dao: FromDishka[TransactionsDAO],
    payment_service: FromDishka[PaymentService],
    **_kwargs,
):
    amount: float = dialog_manager.dialog_data["top_up_amount"]
    url: str = dialog_manager.dialog_data["invoice_url"]
    has_pending = dialog_manager.dialog_data.get("has_pending_transaction", False)
    amount_usd = await payment_service.byn_to_usd(amount)
    pending_text = (
        "⏳ <b>У вас есть незавершённый платёж</b>\n\n"
        f"Сумма: <b>{fmt_amount(amount)} BYN</b> → <b>{fmt_amount(amount_usd)} USDT</b>\n"
        "Нажмите «Оплатить» чтобы перейти к оплате, "
        "или «Отмена» чтобы отменить."
    )
    new_text = (
        "🤖 <b>CryptoBot (USDT)</b>\n\n"
        f"Сумма: <b>{fmt_amount(amount)} BYN</b> → <b>{fmt_amount(amount_usd)} USDT</b>\n\n"
        "Нажмите «Оплатить» чтобы перейти к оплате в @CryptoBot.\n"
        "После оплаты баланс пополнится автоматически."
    )
    return {
        "amount": amount,
        "url": url,
        "has_pending": has_pending,
        "pending_invoice_text": pending_text,
        "new_invoice_text": new_text,
        "pay_btn": "💳 Оплатить",
        "cancel_btn": "❌ Отмена",
    }


@inject
async def on_top_up_clicked(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    transactions_dao: FromDishka[TransactionsDAO],
):
    pending = await transactions_dao.get_pending_by_user_id(callback.from_user.id)
    if pending and pending.payment_url:
        manager.dialog_data["top_up_amount"] = pending.amount
        manager.dialog_data["invoice_url"] = pending.payment_url
        manager.dialog_data["invoice_id"] = pending.payment_id
        manager.dialog_data["has_pending_transaction"] = True
        await manager.switch_to(BalanceSG.invoice)
    else:
        manager.dialog_data["has_pending_transaction"] = False
        await manager.switch_to(BalanceSG.top_up_amount)


async def on_amount_entered(message: Message, widget: MessageInput, manager: DialogManager):
    text = (message.text or "").strip().replace(",", ".")
    try:
        amount = float(text)
        if not 1 <= amount <= 1000:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите число от 1 до 1000.")
        return
    manager.dialog_data["top_up_amount"] = amount
    await manager.switch_to(BalanceSG.top_up_method)


@inject
async def on_cryptobot_clicked(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    payment_service: FromDishka[PaymentService],
):
    amount: float = manager.dialog_data["top_up_amount"]
    user_id = callback.from_user.id
    payment = await payment_service.create_cryptobot_invoice(user_id, amount)
    manager.dialog_data["invoice_url"] = payment.bot_invoice_url
    manager.dialog_data["invoice_id"] = str(payment.invoice_id)
    manager.dialog_data["has_pending_transaction"] = False
    await manager.switch_to(BalanceSG.invoice)


@inject
async def on_stars_clicked(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    payment_service: FromDishka[PaymentService],
    bot: FromDishka[Bot],
):
    amount: float = manager.dialog_data["top_up_amount"]
    user_id = callback.from_user.id
    stars = await payment_service.byn_to_stars(amount)
    await bot.send_invoice(
        chat_id=user_id,
        title=f"Пополнение баланса на {fmt_amount(amount)} BYN",
        description=f"Пополнение депозита SeatBot на {fmt_amount(amount)} BYN",
        payload=f"stars_topup:{amount}",
        currency="XTR",
        prices=[LabeledPrice(label=f"{fmt_amount(amount)} BYN", amount=stars)],
    )
    await callback.answer("Инвойс отправлен в чат", show_alert=True)


@inject
async def on_cancel_invoice_clicked(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    transactions_dao: FromDishka[TransactionsDAO],
):
    invoice_id: str = manager.dialog_data["invoice_id"]
    transaction = await transactions_dao.get_by_payment_id_for_update(invoice_id)
    if transaction and transaction.status == TransactionStatus.COMPLETED:
        await callback.answer("Платёж уже оплачен, баланс пополнен", show_alert=True)
        await manager.start(MainMenuSG.main, mode=StartMode.RESET_STACK)
        return
    if not transaction or transaction.status != TransactionStatus.PENDING:
        await callback.answer("Платёж уже отменён", show_alert=True)
        await manager.start(MainMenuSG.main, mode=StartMode.RESET_STACK)
        return
    await transactions_dao.update_status(invoice_id, TransactionStatus.FAILED)
    await callback.answer("Платёж отменён", show_alert=True)
    await manager.start(MainMenuSG.main, mode=StartMode.RESET_STACK)


balance_dialog = Dialog(
    Window(
        Format("{balance_text}"),
        Row(
            Button(Format("{top_up_btn}"), id="top_up", on_click=on_top_up_clicked),
            Cancel(Format("{back_btn}")),
        ),
        state=BalanceSG.balance,
        getter=get_balance_data,
    ),
    Window(
        Format("{amount_prompt}"),
        MessageInput(on_amount_entered),
        SwitchTo(Format("{back_btn}"), id="back", state=BalanceSG.balance),
        state=BalanceSG.top_up_amount,
        getter=get_top_up_amount_data,
    ),
    Window(
        Format("{method_prompt}"),
        Button(Format("{cryptobot_btn}"), id="crypto_bot", on_click=on_cryptobot_clicked),
        Button(Format("{stars_btn}"), id="stars", on_click=on_stars_clicked),
        SwitchTo(Format("{back_btn}"), id="back", state=BalanceSG.top_up_amount),
        state=BalanceSG.top_up_method,
        getter=get_top_up_method_data,
    ),
    Window(
        Format("{new_invoice_text}"),
        Row(
            Url(Format("{pay_btn}"), Format("{url}")),
            Button(Format("{cancel_btn}"), id="cancel_invoice", on_click=on_cancel_invoice_clicked),
        ),
        state=BalanceSG.invoice,
        getter=get_invoice_data,
    ),
)
