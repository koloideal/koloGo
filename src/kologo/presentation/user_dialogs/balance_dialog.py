from typing import Any

from aiogram import Bot
from aiogram.types import CallbackQuery, LabeledPrice, Message
from aiogram_dialog import Dialog, DialogManager, StartMode, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Cancel, Row, SwitchTo, Url
from aiogram_dialog.widgets.text import Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from kologo.application.services.payment import PaymentService
from kologo.domain.schemas import TransactionStatus
from kologo.infrastructure.config import AppConfig
from kologo.infrastructure.database.dao import TransactionsDAO, UsersDAO
from kologo.infrastructure.notifications import MessageBuilder, fmt_amount

from .states import BalanceSG, MainMenuSG


@inject
async def get_balance_data(
    dialog_manager: DialogManager,
    users_dao: FromDishka[UsersDAO],
    messages: FromDishka[MessageBuilder],
    **_kwargs: Any,
) -> dict[str, Any]:
    user_id = dialog_manager.middleware_data["event_from_user"].id
    user = await users_dao.get_by_id(user_id)
    if not user:
        return {"balance_text": "Сначала нажмите /start", "top_up_btn": "💳 Пополнить", "back_btn": "⬅️ Назад"}
    return {
        "balance_text": messages.balance_info_text(user.balance, user.is_vip),
        "top_up_btn": "💳 Пополнить",
        "back_btn": "⬅️ Назад",
    }


@inject
async def get_top_up_amount_data(app_config: FromDishka[AppConfig], **_kwargs: Any) -> dict[str, Any]:
    return {
        "amount_prompt": (
            "💳 <b>Пополнение баланса</b>\n\n"
            f"Введите сумму в BYN (от {fmt_amount(app_config.topup_min_byn)} "
            f"до {fmt_amount(app_config.topup_max_byn)}):\nПример: <code>50</code>"
        ),
        "back_btn": "⬅️ Назад",
    }


async def get_top_up_method_data(**_kwargs: Any) -> dict[str, Any]:
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
    **_kwargs: Any,
) -> dict[str, Any]:
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
) -> None:
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


async def on_amount_entered(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    app_config: AppConfig = await manager.middleware_data["dishka_container"].get(AppConfig)
    low, high = app_config.topup_min_byn, app_config.topup_max_byn
    text = (message.text or "").strip().replace(",", ".")
    try:
        amount = float(text)
        if not low <= amount <= high:
            raise ValueError
    except ValueError:
        await message.answer(f"❌ Введите число от {fmt_amount(low)} до {fmt_amount(high)}.")
        return
    manager.dialog_data["top_up_amount"] = amount
    await manager.switch_to(BalanceSG.top_up_method)


@inject
async def on_cryptobot_clicked(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    payment_service: FromDishka[PaymentService],
) -> None:
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
) -> None:
    amount: float = manager.dialog_data["top_up_amount"]
    user_id = callback.from_user.id
    stars = await payment_service.byn_to_stars(amount)
    await bot.send_invoice(
        chat_id=user_id,
        title=f"Пополнение баланса на {fmt_amount(amount)} BYN",
        description=f"Пополнение депозита koloGo на {fmt_amount(amount)} BYN",
        payload=payment_service.stars_payload(amount),
        currency="XTR",
        prices=[LabeledPrice(label=f"{fmt_amount(amount)} BYN", amount=stars)],
    )
    await callback.answer("Инвойс отправлен в чат", show_alert=True)


@inject
async def on_cancel_invoice_clicked(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    payment_service: FromDishka[PaymentService],
) -> None:
    invoice_id: str = manager.dialog_data["invoice_id"]
    status = await payment_service.cancel_cryptobot_invoice(invoice_id)
    if status == TransactionStatus.COMPLETED:
        text = "Платёж уже оплачен, баланс пополнен"
    elif status == TransactionStatus.FAILED:
        text = "Платёж отменён"
    else:
        text = "Платёж не найден"
    await callback.answer(text, show_alert=True)
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
