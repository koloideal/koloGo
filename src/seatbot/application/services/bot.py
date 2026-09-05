from aiogram import Bot
from aiogram.exceptions import (TelegramBadRequest, TelegramForbiddenError,
                                TelegramRetryAfter)
from aiogram.types import BotCommand

from seatbot.infrastructure.config.models import Config
from seatbot.infrastructure.database.dao import UsersDAO


class BotService:
    def __init__(self, bot: Bot, config: Config, users_dao: UsersDAO) -> None:
        self._bot = bot
        self._config = config
        self._users_dao = users_dao

    async def process_set_commands(self) -> None:
        commands = [
            BotCommand(command="start", description="Главное меню"),
            BotCommand(command="admin", description="Панель водителя (только админ)"),
        ]
        await self._bot.set_my_commands(commands)

    async def send_log_to_admin_channel(self, text: str) -> None:
        await self._bot.send_message(
            chat_id=self._config.bot.admin_channel,
            text=text,
        )

    async def notify_user(self, user_id: int, text: str) -> None:
        try:
            await self._bot.send_message(chat_id=user_id, text=text)
        except (TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter):
            pass
