from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram_dialog import DialogManager, ShowMode, StartMode
from dishka import FromDishka

from seatbot.application.interactors.user.create_or_get_user import (
    CreateOrGetUserCommand, CreateOrGetUserInteractor)
from seatbot.application.services.bot import BotService
from seatbot.application.services.payment import PaymentService
from seatbot.infrastructure.database.dao import BookingsDAO, RidesDAO, UsersDAO
from seatbot.infrastructure.notifications import MessageBuilder

from .user_dialogs.states import MainMenuSG, RidesSG

user_router = Router()


@user_router.message(Command("start"))
async def cmd_start(
    message: Message,
    dialog_manager: DialogManager,
    create_or_get_user: FromDishka[CreateOrGetUserInteractor],
) -> None:
    from_user = dialog_manager.middleware_data["event_from_user"]
    await create_or_get_user.execute(
        CreateOrGetUserCommand(
            user_id=from_user.id, username=from_user.username, first_name=from_user.first_name
        )
    )
    await dialog_manager.start(MainMenuSG.main, mode=StartMode.RESET_STACK)


@user_router.callback_query(F.data.startswith("open_ride:"))
async def cb_open_ride(callback: CallbackQuery, dialog_manager: DialogManager) -> None:
    ride_id = int((callback.data or "").split(":", 1)[1])
    await callback.answer()
    await dialog_manager.start(
        RidesSG.detail, data={"ride_id": ride_id}, mode=StartMode.RESET_STACK, show_mode=ShowMode.SEND
    )


@user_router.callback_query(F.data.startswith("ride_origin:"))
async def cb_ride_origin(
    callback: CallbackQuery,
    rides_dao: FromDishka[RidesDAO],
    bookings_dao: FromDishka[BookingsDAO],
) -> None:
    ride_id = int((callback.data or "").split(":", 1)[1])
    ride = await rides_dao.get_by_id(ride_id)
    booking = await bookings_dao.get_by_ride_and_user(ride_id, callback.from_user.id)
    if not ride or not booking or ride.origin_lat is None or ride.origin_lon is None:
        await callback.answer("Место отправления недоступно", show_alert=True)
        return
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer_location(latitude=ride.origin_lat, longitude=ride.origin_lon)


@user_router.message(lambda m: m.successful_payment is not None)
async def on_stars_payment(
    message: Message,
    payment_service: FromDishka[PaymentService],
    messages: FromDishka[MessageBuilder],
    users_dao: FromDishka[UsersDAO],
    bot_service: FromDishka[BotService],
) -> None:
    sp = message.successful_payment
    if not sp:
        return
    charge_id = sp.telegram_payment_charge_id
    payload = sp.invoice_payload
    if not payload.startswith("stars_topup:"):
        return
    try:
        amount_byn = float(payload.split(":", 1)[1])
    except (ValueError, IndexError):
        return
    if not message.from_user:
        return
    user_id = message.from_user.id
    ok = await payment_service.complete_stars_payment(user_id, amount_byn, charge_id)
    if not ok:
        await message.answer("✅ Платёж уже был обработан ранее.")
        return
    user = await users_dao.get_by_id(user_id)
    new_balance = user.balance if user else 0.0
    await message.answer(messages.payment_success_notification(amount_byn, new_balance))
    if user:
        await bot_service.send_log_to_admin(messages.payment_admin_log(user, amount_byn, "Telegram Stars"))
