from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seatbot.domain.schemas import Requisite
from seatbot.infrastructure.database.models import Requisite as OrmRequisite


class RequisitesDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, title: str, value: str) -> Requisite:
        orm = OrmRequisite(title=title, value=value)
        self.session.add(orm)
        await self.session.flush()
        return self._map_to_domain(orm)

    async def get_by_id(self, requisite_id: int) -> Requisite | None:
        result = await self.session.execute(
            select(OrmRequisite).where(OrmRequisite.id == requisite_id)
        )
        orm = result.scalar_one_or_none()
        return self._map_to_domain(orm) if orm else None

    async def list_all(self) -> list[Requisite]:
        result = await self.session.execute(
            select(OrmRequisite).order_by(OrmRequisite.created_at.asc())
        )
        return [self._map_to_domain(orm) for orm in result.scalars().all()]

    async def delete(self, requisite_id: int) -> bool:
        result = await self.session.execute(
            select(OrmRequisite).where(OrmRequisite.id == requisite_id)
        )
        orm = result.scalar_one_or_none()
        if not orm:
            return False
        await self.session.delete(orm)
        return True

    @staticmethod
    def _map_to_domain(orm: OrmRequisite) -> Requisite:
        return Requisite(
            requisite_id=orm.id,
            title=orm.title,
            value=orm.value,
            created_at=orm.created_at,
        )
