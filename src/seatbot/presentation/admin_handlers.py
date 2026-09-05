from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram_dialog import DialogManager, StartMode

from .user_dialogs.states import AdminPanelSG

admin_router = Router()


@admin_router.message(Command("admin"))
async def cmd_admin(message: Message, dialog_manager: DialogManager):
    await dialog_manager.start(AdminPanelSG.main, mode=StartMode.RESET_STACK)
