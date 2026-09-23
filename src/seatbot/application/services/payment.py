from seatbot.domain.schemas import TransactionStatus, TransactionType
from seatbot.infrastructure.cache import CacheKeys, RedisService
from seatbot.infrastructure.database.dao import SettingsDAO, TransactionsDAO, UsersDAO
from seatbot.infrastructure.notifications import MessageBuilder
from seatbot.infrastructure.payments import CryptoBotPayment, CryptoBotPaymentService
from seatbot.infrastructure.scheduling.payment_poller import PaymentStatusPoller

BYN_TO_USD_RATE_KEY = "byn_to_usd_rate"
BYN_TO_USD_RATE_DEFAULT = 3.2
BYN_TO_STARS_RATE_KEY = "byn_to_stars_rate"
BYN_TO_STARS_RATE_DEFAULT = 1.0


class PaymentService:
    def __init__(
        self,
        transactions_dao: TransactionsDAO,
        settings_dao: SettingsDAO,
        cryptobot_service: CryptoBotPaymentService,
        poller: PaymentStatusPoller,
        users_dao: UsersDAO,
        message_builder: MessageBuilder,
        cache: RedisService,
        cache_keys: CacheKeys,
    ) -> None:
        self._transactions_dao = transactions_dao
        self._settings_dao = settings_dao
        self._cryptobot_service = cryptobot_service
        self._poller = poller
        self._users_dao = users_dao
        self._messages = message_builder
        self._cache = cache
        self._cache_keys = cache_keys

    async def get_byn_to_usd_rate(self) -> float:
        cached = await self._cache.get(self._cache_keys.rate_byn_usd)
        if cached is not None:
            return cached
        rate = await self._settings_dao.get_float(BYN_TO_USD_RATE_KEY, BYN_TO_USD_RATE_DEFAULT)
        await self._cache.set(self._cache_keys.rate_byn_usd, rate)
        return rate

    async def set_byn_to_usd_rate(self, rate: float) -> None:
        await self._settings_dao.set_float(BYN_TO_USD_RATE_KEY, rate)
        await self._cache.delete(self._cache_keys.rate_byn_usd)

    async def byn_to_usd(self, byn: float) -> float:
        rate = await self.get_byn_to_usd_rate()
        return round(byn / rate, 2)

    async def get_byn_to_stars_rate(self) -> float:
        cached = await self._cache.get(self._cache_keys.rate_byn_stars)
        if cached is not None:
            return cached
        rate = await self._settings_dao.get_float(BYN_TO_STARS_RATE_KEY, BYN_TO_STARS_RATE_DEFAULT)
        await self._cache.set(self._cache_keys.rate_byn_stars, rate)
        return rate

    async def set_byn_to_stars_rate(self, rate: float) -> None:
        await self._settings_dao.set_float(BYN_TO_STARS_RATE_KEY, rate)
        await self._cache.delete(self._cache_keys.rate_byn_stars)

    async def byn_to_stars(self, byn: float) -> int:
        rate = await self.get_byn_to_stars_rate()
        return max(1, round(byn / rate))

    async def create_cryptobot_invoice(self, user_id: int, amount_byn: float) -> CryptoBotPayment:
        amount_usd = await self.byn_to_usd(amount_byn)
        payment = await self._cryptobot_service.create_payment(amount_usd, "USDT")
        await self._transactions_dao.create(
            user_id=user_id,
            amount=amount_byn,
            type=TransactionType.CRYPTOBOT_TOPUP,
            payment_id=str(payment.invoice_id),
            payment_url=payment.bot_invoice_url,
            status=TransactionStatus.PENDING,
        )
        self._poller.start_polling(str(payment.invoice_id), user_id, amount_byn)
        return payment

    async def complete_stars_payment(
        self, user_id: int, amount_byn: float, telegram_payment_charge_id: str
    ) -> bool:
        existing = await self._transactions_dao.get_by_payment_id(telegram_payment_charge_id)
        if existing:
            return False
        await self._users_dao.increase_balance(user_id, amount_byn)
        await self._transactions_dao.create(
            user_id=user_id,
            amount=amount_byn,
            type=TransactionType.STARS_TOPUP,
            payment_id=telegram_payment_charge_id,
            status=TransactionStatus.COMPLETED,
        )
        return True
