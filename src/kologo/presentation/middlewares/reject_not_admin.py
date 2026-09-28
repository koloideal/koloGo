from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from dishka import AsyncContainer

from kologo.infrastructure.config.models import Config


class RejectNotAdminMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        container: AsyncContainer = data["dishka_container"]
        config: Config = await container.get(Config)

        from_user = data.get("event_from_user")
        if not from_user or from_user.id != config.bot.creator_id:
            if isinstance(event, CallbackQuery):
                await event.answer("🚫 Только для водителя.", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("🚫 Только для водителя.")
            return

        return await handler(event, data)
