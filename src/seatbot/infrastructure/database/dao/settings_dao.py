from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from seatbot.infrastructure.database.models import Setting as OrmSetting


class SettingsDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, key: str, default: str | None = None) -> str | None:
        result = await self.session.execute(select(OrmSetting.value).where(OrmSetting.key == key))
        value = result.scalar_one_or_none()
        return value if value is not None else default

    async def get_float(self, key: str, default: float) -> float:
        value = await self.get(key)
        if value is None:
            return default
        try:
            return float(value)
        except ValueError:
            return default

    async def set(self, key: str, value: str) -> None:
        stmt = (
            insert(OrmSetting)
            .values(key=key, value=value)
            .on_conflict_do_update(
                index_elements=["key"],
                set_={"value": value},
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def set_float(self, key: str, value: float) -> None:
        await self.set(key, str(value))
