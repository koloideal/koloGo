import asyncio

from aiogram import Bot
from aiogram.exceptions import (TelegramBadRequest, TelegramForbiddenError,
                                TelegramRetryAfter)

from seatbot.infrastructure.database.dao import UsersDAO


class BroadcastService:
    def __init__(self, bot: Bot, users_dao: UsersDAO) -> None:
        self._bot = bot
        self._users_dao = users_dao

    async def broadcast(self, text: str) -> tuple[int, int]:
        """Рассылка по всем пользователям. Возвращает (успешно, всего)."""
        users = await self._users_dao.get_all()
        success = 0
        total = len(users)
        for user in users:
            try:
                await self._bot.send_message(chat_id=user.user_id, text=text)
                success += 1
            except (TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter):
                pass
            await asyncio.sleep(0.05)
        return success, total
