from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from seatbot.domain.exceptions import InsufficientBalanceError
from seatbot.domain.schemas import User
from seatbot.infrastructure.database.models import User as OrmUser


class UsersDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: int) -> User | None:
        result = await self.session.execute(select(OrmUser).where(OrmUser.user_id == user_id))
        orm_user = result.scalar_one_or_none()
        return self._map_to_domain(orm_user) if orm_user else None

    async def create(self, user_id: int, username: str | None) -> User:
        stmt = (
            insert(OrmUser)
            .values(user_id=user_id, username=username, balance=0)
            .on_conflict_do_nothing(index_elements=["user_id"])
        )
        await self.session.execute(stmt)
        await self.session.flush()
        result = await self.session.execute(select(OrmUser).where(OrmUser.user_id == user_id))
        orm_user = result.scalar_one()
        return self._map_to_domain(orm_user)

    async def get_or_create(self, user_id: int, username: str | None) -> User:
        user = await self.get_by_id(user_id)
        if user:
            return user
        return await self.create(user_id, username)

    async def update_username(self, user_id: int, username: str | None) -> User | None:
        result = await self.session.execute(select(OrmUser).where(OrmUser.user_id == user_id))
        orm_user = result.scalar_one_or_none()
        if not orm_user:
            return None
        orm_user.username = username
        return self._map_to_domain(orm_user)

    async def increase_balance(self, user_id: int, amount: float) -> User | None:
        result = await self.session.execute(select(OrmUser).where(OrmUser.user_id == user_id))
        orm_user = result.scalar_one_or_none()
        if not orm_user:
            return None
        orm_user.balance += Decimal(str(amount))
        return self._map_to_domain(orm_user)

    async def decrease_balance(self, user_id: int, amount: float) -> User | None:
        result = await self.session.execute(select(OrmUser).where(OrmUser.user_id == user_id))
        orm_user = result.scalar_one_or_none()
        if not orm_user:
            return None
        if orm_user.balance < amount:
            raise InsufficientBalanceError(required=amount, available=float(orm_user.balance))
        orm_user.balance -= Decimal(str(amount))
        return self._map_to_domain(orm_user)

    async def set_balance(self, user_id: int, new_balance: float) -> User | None:
        result = await self.session.execute(select(OrmUser).where(OrmUser.user_id == user_id))
        orm_user = result.scalar_one_or_none()
        if not orm_user:
            return None
        orm_user.balance = Decimal(str(new_balance))
        return self._map_to_domain(orm_user)

    async def ban_user(self, user_id: int) -> User | None:
        result = await self.session.execute(select(OrmUser).where(OrmUser.user_id == user_id))
        orm_user = result.scalar_one_or_none()
        if not orm_user:
            return None
        orm_user.is_banned = True
        return self._map_to_domain(orm_user)

    async def unban_user(self, user_id: int) -> User | None:
        result = await self.session.execute(select(OrmUser).where(OrmUser.user_id == user_id))
        orm_user = result.scalar_one_or_none()
        if not orm_user:
            return None
        orm_user.is_banned = False
        return self._map_to_domain(orm_user)

    async def set_vip(self, user_id: int, is_vip: bool) -> User | None:
        result = await self.session.execute(select(OrmUser).where(OrmUser.user_id == user_id))
        orm_user = result.scalar_one_or_none()
        if not orm_user:
            return None
        orm_user.is_vip = is_vip
        return self._map_to_domain(orm_user)

    async def get_all(self, limit: int = -1) -> list[User]:
        query = select(OrmUser).order_by(OrmUser.registration_date.desc())
        if limit != -1:
            query = query.limit(limit)
        result = await self.session.execute(query)
        return [self._map_to_domain(u) for u in result.scalars().all()]

    async def search_by_username(self, username_part: str) -> list[User]:
        query = select(OrmUser).where(OrmUser.username.ilike(f"%{username_part}%"))
        result = await self.session.execute(query)
        return [self._map_to_domain(u) for u in result.scalars().all()]

    async def count_total_users(self, days: int | None = None) -> int:
        query = select(func.count(OrmUser.user_id))
        if days:
            cutoff = datetime.now(UTC) - timedelta(days=days)
            query = query.where(OrmUser.registration_date >= cutoff)
        result = await self.session.execute(query)
        count = result.scalar_one()
        return int(count) if count else 0

    @staticmethod
    def _map_to_domain(orm_user: OrmUser) -> User:
        return User(
            user_id=orm_user.user_id,
            username=orm_user.username,
            balance=float(orm_user.balance),
            registration_date=orm_user.registration_date,
            is_admin=orm_user.is_admin,
            is_banned=orm_user.is_banned,
            is_vip=orm_user.is_vip,
        )
