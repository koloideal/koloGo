from kologo.application.services.bot import BotService
from kologo.domain.exceptions import InsufficientBalanceError
from kologo.domain.schemas import TransactionType, User
from kologo.infrastructure.cache import CacheKeys, RedisService
from kologo.infrastructure.config.app import AppConfig
from kologo.infrastructure.database.dao import SettingsDAO, TransactionsDAO, UsersDAO
from kologo.infrastructure.notifications import MessageBuilder


class VipService:
    def __init__(
        self,
        settings_dao: SettingsDAO,
        users_dao: UsersDAO,
        transactions_dao: TransactionsDAO,
        bot_service: BotService,
        message_builder: MessageBuilder,
        cache: RedisService,
        cache_keys: CacheKeys,
        app_config: AppConfig,
    ) -> None:
        self._settings_dao = settings_dao
        self._users_dao = users_dao
        self._transactions_dao = transactions_dao
        self._bot_service = bot_service
        self._messages = message_builder
        self._cache = cache
        self._cache_keys = cache_keys
        self._app_config = app_config

    async def get_vip_price(self) -> float:
        cached = await self._cache.get(self._cache_keys.vip_price)
        if cached is not None:
            return cached
        price = await self._settings_dao.get_float(
            self._app_config.vip_price_key, self._app_config.vip_price_default
        )
        await self._cache.set(self._cache_keys.vip_price, price)
        return price

    async def set_vip_price(self, price: float) -> None:
        await self._settings_dao.set_float(self._app_config.vip_price_key, price)
        await self._cache.delete(self._cache_keys.vip_price)

    async def purchase_vip(self, user: User) -> User:
        if user.is_vip:
            return user
        price = await self.get_vip_price()
        if user.balance < price:
            raise InsufficientBalanceError(required=price, available=user.balance)
        updated = await self._users_dao.decrease_balance(user.user_id, price)
        if not updated:
            raise InsufficientBalanceError(required=price, available=0.0)
        await self._users_dao.set_vip(user.user_id, True)
        await self._transactions_dao.create(
            user_id=user.user_id,
            amount=price,
            type=TransactionType.VIP_PURCHASE,
        )
        await self._cache.delete(self._cache_keys.user_vip, user_id=user.user_id)
        await self._cache.delete(self._cache_keys.users_stats)
        result = await self._users_dao.get_by_id(user.user_id)
        if result is None:
            raise InsufficientBalanceError(required=price, available=0.0)
        await self._bot_service.notify_user(
            user.user_id, self._messages.vip_purchase_notification(price, result.balance)
        )
        await self._bot_service.send_log_to_admin(self._messages.vip_purchased_admin_log(result, price))
        return result
