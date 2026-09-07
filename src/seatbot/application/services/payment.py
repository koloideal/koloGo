from seatbot.domain.schemas import TransactionStatus, TransactionType
from seatbot.infrastructure.database.dao import SettingsDAO, TransactionsDAO
from seatbot.infrastructure.payments import CryptoBotPayment, CryptoBotPaymentService
from seatbot.infrastructure.scheduling.payment_poller import PaymentStatusPoller

BYN_TO_USD_RATE_KEY = "byn_to_usd_rate"
BYN_TO_USD_RATE_DEFAULT = 3.2


class PaymentService:
    def __init__(
        self,
        transactions_dao: TransactionsDAO,
        settings_dao: SettingsDAO,
        cryptobot_service: CryptoBotPaymentService,
        poller: PaymentStatusPoller,
    ) -> None:
        self._transactions_dao = transactions_dao
        self._settings_dao = settings_dao
        self._cryptobot_service = cryptobot_service
        self._poller = poller

    async def get_byn_to_usd_rate(self) -> float:
        return await self._settings_dao.get_float(BYN_TO_USD_RATE_KEY, BYN_TO_USD_RATE_DEFAULT)

    async def set_byn_to_usd_rate(self, rate: float) -> None:
        await self._settings_dao.set_float(BYN_TO_USD_RATE_KEY, rate)

    async def byn_to_usd(self, byn: float) -> float:
        rate = await self.get_byn_to_usd_rate()
        return round(byn / rate, 2)

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
