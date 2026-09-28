from kologo.application.services.bot import BotService
from kologo.domain.schemas import Transaction, TransactionStatus, TransactionType
from kologo.infrastructure.cache import CacheKeys, RedisService
from kologo.infrastructure.config.app import AppConfig
from kologo.infrastructure.database.dao import SettingsDAO, TransactionsDAO, UsersDAO
from kologo.infrastructure.notifications import MessageBuilder
from kologo.infrastructure.payments import CryptoBotPayment, CryptoBotPaymentService
from kologo.infrastructure.scheduling.payment_poller import PaymentStatusPoller
from kologo.infrastructure.time import LocalClock


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
        bot_service: BotService,
        clock: LocalClock,
        app_config: AppConfig,
    ) -> None:
        self._transactions_dao = transactions_dao
        self._settings_dao = settings_dao
        self._cryptobot_service = cryptobot_service
        self._poller = poller
        self._users_dao = users_dao
        self._messages = message_builder
        self._cache = cache
        self._cache_keys = cache_keys
        self._bot_service = bot_service
        self._clock = clock
        self._app_config = app_config

    async def get_byn_to_usd_rate(self) -> float:
        cached = await self._cache.get(self._cache_keys.rate_byn_usd)
        if cached is not None:
            return cached
        rate = await self._settings_dao.get_float(
            self._app_config.byn_to_usd_rate_key, self._app_config.byn_to_usd_rate_default
        )
        await self._cache.set(self._cache_keys.rate_byn_usd, rate)
        return rate

    async def set_byn_to_usd_rate(self, rate: float) -> None:
        await self._settings_dao.set_float(self._app_config.byn_to_usd_rate_key, rate)
        await self._cache.delete(self._cache_keys.rate_byn_usd)

    async def byn_to_usd(self, byn: float) -> float:
        rate = await self.get_byn_to_usd_rate()
        return round(byn / rate, 2)

    async def get_byn_to_stars_rate(self) -> float:
        cached = await self._cache.get(self._cache_keys.rate_byn_stars)
        if cached is not None:
            return cached
        rate = await self._settings_dao.get_float(
            self._app_config.byn_to_stars_rate_key, self._app_config.byn_to_stars_rate_default
        )
        await self._cache.set(self._cache_keys.rate_byn_stars, rate)
        return rate

    async def set_byn_to_stars_rate(self, rate: float) -> None:
        await self._settings_dao.set_float(self._app_config.byn_to_stars_rate_key, rate)
        await self._cache.delete(self._cache_keys.rate_byn_stars)

    async def byn_to_stars(self, byn: float) -> int:
        rate = await self.get_byn_to_stars_rate()
        return max(1, round(byn / rate))

    # ── CryptoBot ────────────────────────────────────────────────────────────

    async def create_cryptobot_invoice(self, user_id: int, amount_byn: float) -> CryptoBotPayment:
        amount_usd = await self.byn_to_usd(amount_byn)
        payment = await self._cryptobot_service.create_payment(
            amount_usd, "USDT", expires_in=int(self._app_config.cryptobot_invoice_ttl.total_seconds())
        )
        await self._transactions_dao.create(
            user_id=user_id,
            amount=amount_byn,
            type=TransactionType.CRYPTOBOT_TOPUP,
            payment_id=str(payment.invoice_id),
            payment_url=payment.bot_invoice_url,
            status=TransactionStatus.PENDING,
        )
        self._poller.start_polling(str(payment.invoice_id))
        return payment

    async def resume_pending_polling(self) -> int:
        pending = await self._transactions_dao.list_pending_cryptobot()
        for tx in pending:
            if tx.payment_id:
                self._poller.start_polling(tx.payment_id)
        return len(pending)

    async def process_cryptobot_invoice(self, payment_id: str) -> TransactionStatus | None:
        tx = await self._transactions_dao.get_by_payment_id_for_update(payment_id)
        if not tx or tx.status != TransactionStatus.PENDING:
            return tx.status if tx else None
        if await self._cryptobot_service.check_payment(payment_id) == "paid":
            await self._complete_cryptobot(tx)
            return TransactionStatus.COMPLETED
        if self._clock.now() - tx.created_at > self._app_config.cryptobot_invoice_ttl:
            await self._cryptobot_service.delete_invoice(payment_id)
            await self._transactions_dao.update_status(payment_id, TransactionStatus.FAILED)
            await self._bot_service.notify_user(tx.user_id, self._messages.payment_expired_notification())
            return TransactionStatus.FAILED
        return TransactionStatus.PENDING

    async def cancel_cryptobot_invoice(self, payment_id: str) -> TransactionStatus | None:
        tx = await self._transactions_dao.get_by_payment_id_for_update(payment_id)
        if not tx or tx.status != TransactionStatus.PENDING:
            return tx.status if tx else None
        # клиент мог оплатить за секунду до отмены — сначала проверяем
        if await self._cryptobot_service.check_payment(payment_id) == "paid":
            await self._complete_cryptobot(tx)
            return TransactionStatus.COMPLETED
        await self._cryptobot_service.delete_invoice(payment_id)
        await self._transactions_dao.update_status(payment_id, TransactionStatus.FAILED)
        return TransactionStatus.FAILED

    async def _complete_cryptobot(self, tx: Transaction) -> None:
        assert tx.payment_id is not None
        await self._transactions_dao.update_status(tx.payment_id, TransactionStatus.COMPLETED)
        user = await self._users_dao.increase_balance(tx.user_id, tx.amount)
        await self._cache.delete(self._cache_keys.users_stats)
        if user:
            await self._bot_service.notify_user(
                tx.user_id, self._messages.payment_success_notification(tx.amount, user.balance)
            )
            await self._bot_service.send_log_to_admin(self._messages.payment_admin_log(user, tx.amount))

    # ── Telegram Stars ───────────────────────────────────────────────────────

    def stars_payload(self, amount_byn: float) -> str:
        return f"{self._app_config.stars_payload_prefix}{amount_byn}"

    def parse_stars_payload(self, payload: str) -> float | None:
        prefix = self._app_config.stars_payload_prefix
        if not payload.startswith(prefix):
            return None
        try:
            amount = float(payload.removeprefix(prefix))
        except ValueError:
            return None
        return amount if self._app_config.topup_min_byn <= amount <= self._app_config.topup_max_byn else None

    async def complete_stars_payment(
        self, user_id: int, amount_byn: float, telegram_payment_charge_id: str
    ) -> bool:
        created = await self._transactions_dao.try_create(
            user_id=user_id,
            amount=amount_byn,
            type=TransactionType.STARS_TOPUP,
            payment_id=telegram_payment_charge_id,
            status=TransactionStatus.COMPLETED,
        )
        if created is None:
            return False
        await self._users_dao.increase_balance(user_id, amount_byn)
        await self._cache.delete(self._cache_keys.users_stats)
        return True
