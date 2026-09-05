from .create_or_get_user import CreateOrGetUserCommand, CreateOrGetUserInteractor


class UserFacade:
    def __init__(self, create_or_get_user: CreateOrGetUserInteractor) -> None:
        self._create_or_get_user = create_or_get_user

    async def create_or_get(self, cmd: CreateOrGetUserCommand) -> None:
        await self._create_or_get_user.execute(cmd)
