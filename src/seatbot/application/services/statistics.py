
from seatbot.domain.schemas import OverallStats, RideStatus, UserStats
from seatbot.infrastructure.database.dao import (BookingsDAO, RidesDAO, TransactionsDAO,
                                                 UsersDAO)


class StatisticsService:
    def __init__(
        self,
        users_dao: UsersDAO,
        rides_dao: RidesDAO,
        bookings_dao: BookingsDAO,
        transactions_dao: TransactionsDAO,
    ) -> None:
        self._users_dao = users_dao
        self._rides_dao = rides_dao
        self._bookings_dao = bookings_dao
        self._transactions_dao = transactions_dao

    async def user_stats(self, user_id: int) -> UserStats | None:
        user = await self._users_dao.get_by_id(user_id)
        if not user:
            return None
        total_rides = await self._bookings_dao.count_completed_for_user(user_id)
        total_spent = await self._bookings_dao.sum_paid_for_user(user_id)
        bookings = await self._bookings_dao.list_for_user(user_id, limit=1)
        last_ride_at = bookings[0].created_at if bookings else None
        return UserStats(
            user_id=user.user_id,
            username=user.username,
            total_rides=total_rides,
            total_spent=total_spent,
            balance=user.balance,
            is_vip=user.is_vip,
            is_banned=user.is_banned,
            last_ride_at=last_ride_at,
        )

    async def overall_stats(self) -> OverallStats:
        total_users = await self._users_dao.count_total_users()
        total_rides = await self._rides_dao.count_total()
        completed = await self._rides_dao.count_by_status(RideStatus.COMPLETED)
        revenue = await self._transactions_dao.sum_total_revenue()
        active = await self._rides_dao.count_by_status(RideStatus.OPEN)
        return OverallStats(
            total_users=total_users,
            total_rides_created=total_rides,
            total_completed_rides=completed,
            total_revenue=revenue,
            active_rides=active,
        )

    async def all_users_stats(self, limit: int = 100) -> list[UserStats]:
        users = await self._users_dao.get_all(limit=limit)
        out: list[UserStats] = []
        for user in users:
            total_rides = await self._bookings_dao.count_completed_for_user(user.user_id)
            total_spent = await self._bookings_dao.sum_paid_for_user(user.user_id)
            bookings = await self._bookings_dao.list_for_user(user.user_id, limit=1)
            last_ride_at = bookings[0].created_at if bookings else None
            out.append(
                UserStats(
                    user_id=user.user_id,
                    username=user.username,
                    total_rides=total_rides,
                    total_spent=total_spent,
                    balance=user.balance,
                    is_vip=user.is_vip,
                    is_banned=user.is_banned,
                    last_ride_at=last_ride_at,
                )
            )
        return out
