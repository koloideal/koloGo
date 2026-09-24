import logging

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import ExceptionTypeFilter
from aiogram.types import ErrorEvent
from aiogram_dialog import DialogManager, ShowMode, StartMode
from aiogram_dialog.api.exceptions import (InvalidStackIdError, NoContextError,
                                           OutdatedIntent, UnknownIntent, UnknownState)
from dishka import FromDishka

from seatbot.infrastructure.config.models import Config

from .user_dialogs.states import AdminPanelSG, MainMenuSG

logger = logging.getLogger("seatbot.errors")
error_router = Router()


@error_router.error(
    ExceptionTypeFilter(UnknownIntent, UnknownState, OutdatedIntent, NoContextError, InvalidStackIdError)
)
async def on_stale_dialog(
    event: ErrorEvent,
    config: FromDishka[Config],
    dialog_manager: DialogManager | None = None,
) -> None:
    logger.info("Stale dialog event: %r", event.exception)
    if dialog_manager is None:
        return
    update = event.update
    callback = update.callback_query
    user_id = None
    if callback is not None:
        user_id = callback.from_user.id
        try:
            await callback.answer("Диалог устарел — открываю меню")
        except TelegramBadRequest:
            pass
    elif update.message is not None and update.message.from_user is not None:
        user_id = update.message.from_user.id
    state = AdminPanelSG.main if user_id == config.bot.creator_id else MainMenuSG.main
    try:
        await dialog_manager.start(state, mode=StartMode.RESET_STACK, show_mode=ShowMode.SEND)
    except Exception:
        logger.exception("Failed to reset dialog to main menu")


@error_router.error()
async def on_error(event: ErrorEvent) -> None:
    logger.exception("Unhandled exception", exc_info=event.exception)
