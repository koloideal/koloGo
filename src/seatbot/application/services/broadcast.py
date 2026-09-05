import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import (TelegramBadRequest, TelegramForbiddenError,
                                TelegramRetryAfter)

from seatbot.infrastructure.config.models import Config
from seatbot.infrastructure.database.dao import UsersDAO

logger = logging.getLogger(__name__)


class BroadcastService:
    def __init__(self, bot: Bot, config: Config, users_dao: UsersDAO) -> None:
        self._bot = bot
        self._config = config
        self._users_dao = users_dao

    async def broadcast_message(
        self,
        from_chat_id: int,
        message_id: int,
    ) -> tuple[int, int]:
        """Копирует сообщение всем пользователям через copy_message.

        Возвращает (успешно, всего). Админу (creator_id) не отправляет.
        """
        users = await self._users_dao.get_all(exclude_user_id=self._config.bot.creator_id)
        success = 0
        total = len(users)
        for user in users:
            try:
                await self._bot.copy_message(
                    chat_id=user.user_id,
                    from_chat_id=from_chat_id,
                    message_id=message_id,
                )
                success += 1
            except (TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter):
                pass
            except Exception:
                logger.exception("broadcast: failed to send to user %s", user.user_id)
            await asyncio.sleep(0.05)
        return success, total

    async def broadcast_message_and_report(
        self,
        from_chat_id: int,
        message_id: int,
    ) -> None:
        """Запускает рассылку и отправляет стату админу по завершении."""
        success, total = await self.broadcast_message(from_chat_id, message_id)
        failed = total - success
        report = (
            f"📊 <b>Рассылка завершена</b>\n\n"
            f"✅ Доставлено: <b>{success}</b>\n"
            f"❌ Не доставлено: <b>{failed}</b>\n"
            f"👥 Всего: <b>{total}</b>"
        )
        try:
            await self._bot.send_message(
                chat_id=self._config.bot.creator_id,
                text=report,
            )
        except (TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter):
            pass

    def start_broadcast(
        self,
        from_chat_id: int,
        message_id: int,
    ) -> asyncio.Task[None]:
        """Запускает рассылку в фоне, не блокируя вызывающий код."""
        return asyncio.create_task(
            self.broadcast_message_and_report(from_chat_id, message_id)
        )
