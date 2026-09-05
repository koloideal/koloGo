from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram_dialog import DialogManager, StartMode
from dishka import FromDishka

from seatbot.application.interactors.user.create_or_get_user import (
    CreateOrGetUserCommand, CreateOrGetUserInteractor)

from .user_dialogs.states import MainMenuSG

user_router = Router()


@user_router.message(Command("start"))
async def cmd_start(
    message: Message,
    dialog_manager: DialogManager,
    create_or_get_user: FromDishka[CreateOrGetUserInteractor],
):
    from_user = dialog_manager.middleware_data["event_from_user"]
    await create_or_get_user.execute(
        CreateOrGetUserCommand(user_id=from_user.id, username=from_user.username)
    )
    await dialog_manager.start(MainMenuSG.main, mode=StartMode.RESET_STACK)
