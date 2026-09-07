from dataclasses import dataclass

from seatbot.application.services.bot import BotService
from seatbot.infrastructure.database.dao import UsersDAO
from seatbot.infrastructure.notifications import MessageBuilder


@dataclass(frozen=True)
class CreateOrGetUserCommand:
    user_id: int
    username: str | None
    first_name: str | None = None


class CreateOrGetUserInteractor:
    def __init__(self, users_dao: UsersDAO, bot_service: BotService, message_builder: MessageBuilder) -> None:
        self._users_dao = users_dao
        self._bot_service = bot_service
        self._messages = message_builder

    async def execute(self, cmd: CreateOrGetUserCommand) -> None:
        existing = await self._users_dao.get_by_id(cmd.user_id)
        if existing:
            if existing.username != cmd.username or existing.first_name != cmd.first_name:
                await self._users_dao.update_profile(cmd.user_id, cmd.username, cmd.first_name)
            return

        user = await self._users_dao.create(
            user_id=cmd.user_id, username=cmd.username, first_name=cmd.first_name
        )
        await self._bot_service.send_log_to_admin(self._messages.new_user_admin_log(user))
