import logging
from collections.abc import Awaitable, Callable

from aiogram.exceptions import TelegramAPIError
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

type PostCommitAction = Callable[[], Awaitable[object]]


class PostCommit:
    __slots__ = ("_actions",)

    def __init__(self) -> None:
        self._actions: list[PostCommitAction] = []

    def add(self, action: PostCommitAction) -> None:
        self._actions.append(action)

    async def run(self) -> None:
        actions, self._actions = self._actions, []
        for action in actions:
            try:
                await action()
            except (TelegramAPIError, RedisError):
                logger.exception("Post-commit action failed")
