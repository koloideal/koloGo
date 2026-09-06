from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from seatbot.domain.schemas import Transaction, TransactionType
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
    ) -> Transaction:
        orm = OrmTransaction(
            user_id=user_id,
            amount=amount,
            type=type.value,
            ride_id=ride_id,
        )
        self.session.add(orm)
        await self.session.flush()
        return self._map_to_domain(orm)

    async def list_for_user(self, user_id: int, limit: int = 20) -> list[Transaction]:
        result = await self.session.execute(
            select(OrmTransaction)
            .where(OrmTransaction.user_id == user_id)
            .order_by(OrmTransaction.created_at.desc())
            .limit(limit)
        )
        return [self._map_to_domain(t) for t in result.scalars().all()]

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
        )
