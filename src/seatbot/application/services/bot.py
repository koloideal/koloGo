from aiogram import Bot
from aiogram.exceptions import (TelegramBadRequest, TelegramForbiddenError,
                                TelegramRetryAfter)
from aiogram.types import (BotCommand, BotCommandScopeChat, BufferedInputFile,
                           InlineKeyboardMarkup)

from seatbot.infrastructure.config.models import Config
from seatbot.infrastructure.database.dao import UsersDAO


class BotService:
    def __init__(self, bot: Bot, config: Config, users_dao: UsersDAO) -> None:
        self._bot = bot
        self._config = config
        self._users_dao = users_dao

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
        await self._bot.send_message(
            chat_id=self._config.bot.creator_id,
            text=text,
            reply_markup=reply_markup,
        )

    async def notify_user(self, user_id: int, text: str) -> bool:
        try:
            await self._bot.send_message(chat_id=user_id, text=text)
            return True
        except (TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter):
            return False

    async def send_track_map(self, chat_id: int, png: bytes, caption: str = "") -> bool:
        try:
            await self._bot.send_photo(
                chat_id=chat_id,
                photo=BufferedInputFile(png, filename="track.png"),
                caption=caption,
            )
            return True
        except (TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter):
            return False
