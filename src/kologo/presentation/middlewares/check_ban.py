from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from dishka import AsyncContainer

from kologo.application.services.user import UserService


class CheckBanMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        update = event
        if not isinstance(update, Update):
            return await handler(event, data)

        user_id = None
        if update.message and update.message.from_user:
            user_id = update.message.from_user.id
        elif update.callback_query and update.callback_query.from_user:
            user_id = update.callback_query.from_user.id

        if not user_id:
            return await handler(event, data)

        container: AsyncContainer = data["dishka_container"]
        user_service: UserService = await container.get(UserService)

        is_banned = await user_service.is_banned(user_id)
        if is_banned:
            text = "🚫 Вы в чёрном списке. Бронирование недоступно."
            if update.message:
                await update.message.answer(text)
            elif update.callback_query:
                await update.callback_query.answer(text, show_alert=True)
            return

        return await handler(event, data)
