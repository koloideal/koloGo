from dataclasses import dataclass

from seatbot.application.services.bot import BotService
from seatbot.infrastructure.database.dao import UsersDAO
from seatbot.infrastructure.notifications import MessageBuilder


@dataclass(frozen=True)
class CreateOrGetUserCommand:
    user_id: int
    username: str | None


class CreateOrGetUserInteractor:
    def __init__(self, users_dao: UsersDAO, bot_service: BotService) -> None:
        self._users_dao = users_dao
        self._bot_service = bot_service

    async def execute(self, cmd: CreateOrGetUserCommand) -> None:
        existing = await self._users_dao.get_by_id(cmd.user_id)
        if existing:
            if existing.username != cmd.username:
                await self._users_dao.update_username(cmd.user_id, cmd.username)
            return

        user = await self._users_dao.create(user_id=cmd.user_id, username=cmd.username)
        await self._bot_service.send_log_to_admin(
            MessageBuilder.new_user_admin_log(user)
        )
