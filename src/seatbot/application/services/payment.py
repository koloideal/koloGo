from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dishka import AsyncContainer

from seatbot.domain.schemas import TransactionStatus, TransactionType
from seatbot.infrastructure.database.dao import TransactionsDAO
from seatbot.infrastructure.payments import CryptoBotPayment, CryptoBotPaymentService
from seatbot.infrastructure.scheduling.tasks import check_cryptobot_payment_status


class PaymentService:
    def __init__(
        self,
        transactions_dao: TransactionsDAO,
        cryptobot_service: CryptoBotPaymentService,
        scheduler: AsyncIOScheduler,
        container: AsyncContainer,
    ) -> None:
        self._transactions_dao = transactions_dao
        self._cryptobot_service = cryptobot_service
        self._scheduler = scheduler
        self._container = container

    async def create_cryptobot_invoice(self, user_id: int, amount: float) -> CryptoBotPayment:
        payment = await self._cryptobot_service.create_payment(amount, "USDT")
        await self._transactions_dao.create(
            user_id=user_id,
            amount=amount,
            type=TransactionType.CRYPTOBOT_TOPUP,
            payment_id=str(payment.invoice_id),
            payment_url=payment.bot_invoice_url,
            status=TransactionStatus.PENDING,
        )
        self._scheduler.add_job(
            check_cryptobot_payment_status,
            trigger="interval",
            seconds=5,
            id=f"check_payment_{payment.invoice_id}",
            kwargs={
                "payment_id": str(payment.invoice_id),
                "user_id": user_id,
                "amount": amount,
                "created_at": datetime.now(UTC),
                "container": self._container,
            },
            max_instances=5,
        )
        return payment
