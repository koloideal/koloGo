from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from seatbot.domain.schemas import Transaction, TransactionStatus, TransactionType
from seatbot.infrastructure.database.models import Transaction as OrmTransaction


class TransactionsDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        user_id: int,
        amount: float,
        type: TransactionType,
        ride_id: int | None = None,
        payment_id: str | None = None,
        payment_url: str | None = None,
        status: TransactionStatus = TransactionStatus.COMPLETED,
    ) -> Transaction:
        orm = OrmTransaction(
            user_id=user_id,
            amount=amount,
            type=type.value,
            ride_id=ride_id,
            payment_id=payment_id,
            payment_url=payment_url,
            status=status.value,
        )
        self.session.add(orm)
        await self.session.flush()
        return self._map_to_domain(orm)

    async def try_create(
        self,
        user_id: int,
        amount: float,
        type: TransactionType,
        payment_id: str,
        status: TransactionStatus = TransactionStatus.COMPLETED,
    ) -> Transaction | None:
        try:
            async with self.session.begin_nested():
                return await self.create(
                    user_id=user_id, amount=amount, type=type, payment_id=payment_id, status=status
                )
        except IntegrityError:
            return None

    async def get_by_payment_id(self, payment_id: str) -> Transaction | None:
        result = await self.session.execute(
            select(OrmTransaction).where(OrmTransaction.payment_id == payment_id)
        )
        orm = result.scalar_one_or_none()
        return self._map_to_domain(orm) if orm else None

    async def get_by_payment_id_for_update(self, payment_id: str) -> Transaction | None:
        result = await self.session.execute(
            select(OrmTransaction).where(OrmTransaction.payment_id == payment_id).with_for_update()
        )
        orm = result.scalar_one_or_none()
        return self._map_to_domain(orm) if orm else None

    async def update_status(self, payment_id: str, new_status: TransactionStatus) -> Transaction | None:
        result = await self.session.execute(
            select(OrmTransaction).where(OrmTransaction.payment_id == payment_id)
        )
        orm = result.scalar_one_or_none()
        if not orm:
            return None
        orm.status = new_status.value
        await self.session.flush()
        return self._map_to_domain(orm)

    async def get_pending_by_user_id(self, user_id: int) -> Transaction | None:
        result = await self.session.execute(
            select(OrmTransaction)
            .where(
                OrmTransaction.user_id == user_id,
                OrmTransaction.payment_url.is_not(None),
                OrmTransaction.status == TransactionStatus.PENDING.value,
            )
            .order_by(OrmTransaction.created_at.desc())
            .limit(1)
        )
        orm = result.scalar_one_or_none()
        return self._map_to_domain(orm) if orm else None

    async def list_pending_cryptobot(self) -> list[Transaction]:
        result = await self.session.execute(
            select(OrmTransaction).where(
                OrmTransaction.type == TransactionType.CRYPTOBOT_TOPUP.value,
                OrmTransaction.status == TransactionStatus.PENDING.value,
                OrmTransaction.payment_id.is_not(None),
            )
        )
        return [self._map_to_domain(orm) for orm in result.scalars().all()]

    async def sum_total_revenue(self) -> float:
        paid = await self._sum_by_type(TransactionType.RIDE_PAYMENT)
        refunded = await self._sum_by_type(TransactionType.REFUND)
        return paid - refunded

    async def _sum_by_type(self, type: TransactionType) -> float:
        result = await self.session.execute(
            select(func.coalesce(func.sum(OrmTransaction.amount), 0)).where(OrmTransaction.type == type.value)
        )
        return float(result.scalar_one() or 0)

    @staticmethod
    def _map_to_domain(orm: OrmTransaction) -> Transaction:
        return Transaction(
            transaction_id=orm.id,
            user_id=orm.user_id,
            amount=float(orm.amount),
            type=TransactionType(orm.type),
            ride_id=orm.ride_id,
            created_at=orm.created_at,
            payment_id=orm.payment_id,
            payment_url=orm.payment_url,
            status=TransactionStatus(orm.status),
        )
