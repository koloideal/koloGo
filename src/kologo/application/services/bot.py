import asyncio

from aiogram import Bot
from aiogram.exceptions import (TelegramBadRequest, TelegramForbiddenError,
                                TelegramRetryAfter)
from aiogram.types import BotCommand, BotCommandScopeChat, InlineKeyboardMarkup

from kologo.infrastructure.config.models import Config
from kologo.infrastructure.database.dao import UsersDAO
from kologo.infrastructure.post_commit import PostCommit


class BotService:
    def __init__(self, bot: Bot, config: Config, users_dao: UsersDAO, post_commit: PostCommit) -> None:
        self._bot = bot
        self._config = config
        self._users_dao = users_dao
        self._post_commit = post_commit

    @property
    def creator_id(self) -> int:
        return self._config.bot.creator_id

    async def process_set_commands(self) -> None:
        start_command = BotCommand(command="start", description="Главное меню")
        await self._bot.set_my_commands([start_command])
        await self._bot.set_my_commands(
            [
                start_command,
                BotCommand(command="admin", description="Панель водителя"),
            ],
            scope=BotCommandScopeChat(chat_id=self._config.bot.creator_id),
        )

    async def send_log_to_admin(self, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
        self._post_commit.add(lambda: self.notify_user_now(self._config.bot.creator_id, text, reply_markup))

    async def notify_user(
        self, user_id: int, text: str, reply_markup: InlineKeyboardMarkup | None = None
    ) -> None:
        self._post_commit.add(lambda: self.notify_user_now(user_id, text, reply_markup))

    async def notify_user_now(
        self, user_id: int, text: str, reply_markup: InlineKeyboardMarkup | None = None
    ) -> bool:
        for _ in range(2):
            try:
                await self._bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup)
                return True
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
            except (TelegramForbiddenError, TelegramBadRequest):
                return False
        return False
