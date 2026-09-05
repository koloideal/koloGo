from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from aiogram_dialog import DialogManager, StartMode
from dishka import FromDishka

from seatbot.application.interactors.user.create_or_get_user import (
    CreateOrGetUserCommand, CreateOrGetUserInteractor)

from .user_dialogs.states import BalanceSG, MainMenuSG, MyBookingsSG, RidesSG

user_router = Router()


@user_router.message(Command("start"))
async def cmd_start(
    message: Message,
    command: CommandObject,
    dialog_manager: DialogManager,
    create_or_get_user: FromDishka[CreateOrGetUserInteractor],
):
    from_user = dialog_manager.middleware_data["event_from_user"]
    await create_or_get_user.execute(
        CreateOrGetUserCommand(user_id=from_user.id, username=from_user.username)
    )
    await dialog_manager.start(MainMenuSG.main, mode=StartMode.RESET_STACK)


@user_router.message(Command("rides"))
async def cmd_rides(message: Message, dialog_manager: DialogManager):
    await dialog_manager.start(RidesSG.list, mode=StartMode.RESET_STACK)


@user_router.message(Command("mybookings"))
async def cmd_mybookings(message: Message, dialog_manager: DialogManager):
    await dialog_manager.start(MyBookingsSG.list, mode=StartMode.RESET_STACK)


@user_router.message(Command("balance"))
async def cmd_balance(message: Message, dialog_manager: DialogManager):
    await dialog_manager.start(BalanceSG.balance, mode=StartMode.RESET_STACK)
