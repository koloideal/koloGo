from datetime import UTC, datetime, timedelta

from dishka import AsyncContainer

from seatbot.domain.schemas import RideStatus
from seatbot.infrastructure.database.dao import RidesDAO


async def auto_close_past_rides(container: AsyncContainer) -> None:
    """Закрывает поездки, время отправления которых прошло более 30 минут назад."""
    async with container() as scope:
        rides_dao: RidesDAO = await scope.get(RidesDAO)

        now = datetime.now(UTC)
        active_rides = await rides_dao.list_active()
        for ride in active_rides:
            if ride.departure_at < now - timedelta(minutes=30):
                await rides_dao.set_status(ride.ride_id, RideStatus.CLOSED)
