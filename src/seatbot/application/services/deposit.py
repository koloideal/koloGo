from seatbot.application.services.bot import BotService
from seatbot.domain.schemas import TransactionType, User
from seatbot.infrastructure.database.dao import TransactionsDAO, UsersDAO
from seatbot.infrastructure.notifications import MessageBuilder


class DepositService:
    def __init__(
        self,
        users_dao: UsersDAO,
        transactions_dao: TransactionsDAO,
        bot_service: BotService,
    ) -> None:
        self._users_dao = users_dao
        self._transactions_dao = transactions_dao
        self._bot_service = bot_service

    async def topup(self, user_id: int, amount: float) -> User | None:
        if amount <= 0:
            return None
        user = await self._users_dao.increase_balance(user_id, amount)
        if not user:
            return None
        await self._transactions_dao.create(
            user_id=user_id,
            amount=amount,
            type=TransactionType.ADMIN_TOPUP,
        )
        await self._bot_service.notify_user(
            user_id, MessageBuilder.deposit_topup_notification(amount, user.balance)
        )
        return user

    async def decrease(self, user_id: int, amount: float) -> User | None:
        if amount <= 0:
            return None
        user = await self._users_dao.decrease_balance(user_id, amount)
        if not user:
            return None
        await self._transactions_dao.create(
            user_id=user_id,
            amount=amount,
            type=TransactionType.ADMIN_DECREASE,
        )
        await self._bot_service.notify_user(
            user_id, MessageBuilder.deposit_decrease_notification(amount, user.balance)
        )
        return user
