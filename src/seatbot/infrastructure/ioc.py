from collections.abc import AsyncIterable
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dishka import AsyncContainer, Provider, Scope, provide
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from seatbot.application.interactors.user.create_or_get_user import \
    CreateOrGetUserInteractor
from seatbot.application.services.bot import BotService
from seatbot.application.services.broadcast import BroadcastService
from seatbot.application.services.deposit import DepositService
from seatbot.application.services.ride import RideService
from seatbot.application.services.statistics import StatisticsService
from seatbot.application.services.user import UserService
from seatbot.application.services.vip import VipService
from seatbot.infrastructure.cache import CacheKeys, RedisService
from seatbot.infrastructure.config.models import Config
from seatbot.infrastructure.database.config import new_session_maker
from seatbot.infrastructure.database.dao import (BookingsDAO, RequisitesDAO, RidesDAO,
                                                 SettingsDAO, TransactionsDAO, UsersDAO)
from seatbot.infrastructure.notifications import MessageBuilder
from seatbot.infrastructure.scheduling.tasks import (auto_close_past_rides,
                                                     send_ride_reminders)
from seatbot.infrastructure.time import LocalClock


class DatabaseProvider(Provider):
    scope = Scope.REQUEST

    @provide(scope=Scope.APP)
    def get_session_maker(self, config: Config) -> async_sessionmaker[AsyncSession]:
        return new_session_maker(config.postgres.dsn)

    @provide
    async def get_session(
        self, session_maker: async_sessionmaker[AsyncSession]
    ) -> AsyncIterable[AsyncSession]:
        async with session_maker() as session, session.begin():
            yield session

    @provide
    def get_users_dao(self, session: AsyncSession) -> UsersDAO:
        return UsersDAO(session)

    @provide
    def get_rides_dao(self, session: AsyncSession) -> RidesDAO:
        return RidesDAO(session)

    @provide
    def get_bookings_dao(self, session: AsyncSession) -> BookingsDAO:
        return BookingsDAO(session)

    @provide
    def get_transactions_dao(self, session: AsyncSession) -> TransactionsDAO:
        return TransactionsDAO(session)

    @provide
    def get_requisites_dao(self, session: AsyncSession) -> RequisitesDAO:
        return RequisitesDAO(session)

    @provide
    def get_settings_dao(self, session: AsyncSession) -> SettingsDAO:
        return SettingsDAO(session)


class RedisProvider(Provider):
    scope = Scope.APP

    @provide
    async def get_redis(self, config: Config) -> AsyncIterable[Redis]:
        redis: Redis = Redis.from_url(
            config.redis.cache_dsn,
            decode_responses=True,
            max_connections=5,
        )
        try:
            yield redis
        finally:
            await redis.aclose()

    @provide(scope=Scope.REQUEST)
    def get_cache_service(self, redis: Redis) -> RedisService:
        return RedisService(redis)

    @provide(scope=Scope.APP)
    def get_cache_keys(self) -> CacheKeys:
        return CacheKeys()


class TimeProvider(Provider):
    scope = Scope.APP

    @provide
    def get_local_clock(self, config: Config) -> LocalClock:
        return LocalClock(ZoneInfo(config.bot.timezone))


class SchedulerProvider(Provider):
    @provide(scope=Scope.APP)
    def get_scheduler(self, async_container: AsyncContainer) -> AsyncIOScheduler:
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            func=auto_close_past_rides,
            trigger=IntervalTrigger(minutes=5),
            kwargs={"container": async_container},
            name="auto_close_past_rides",
        )
        scheduler.add_job(
            func=send_ride_reminders,
            trigger=IntervalTrigger(minutes=1),
            kwargs={"container": async_container},
            name="send_ride_reminders",
        )
        return scheduler


class ServicesProvider(Provider):
    scope = Scope.REQUEST

    @provide
    def get_message_builder(self, clock: LocalClock) -> MessageBuilder:
        return MessageBuilder(clock)

    @provide
    def get_user_service(
        self, cache: RedisService, cache_keys: CacheKeys, users_dao: UsersDAO
    ) -> UserService:
        return UserService(cache, cache_keys, users_dao)

    @provide
    def get_ride_service(
        self,
        rides_dao: RidesDAO,
        bookings_dao: BookingsDAO,
        users_dao: UsersDAO,
        transactions_dao: TransactionsDAO,
        bot_service: BotService,
        message_builder: MessageBuilder,
        clock: LocalClock,
    ) -> RideService:
        return RideService(
            rides_dao, bookings_dao, users_dao, transactions_dao, bot_service, message_builder, clock
        )

    @provide
    def get_deposit_service(
        self,
        users_dao: UsersDAO,
        transactions_dao: TransactionsDAO,
        bot_service: BotService,
        message_builder: MessageBuilder,
    ) -> DepositService:
        return DepositService(users_dao, transactions_dao, bot_service, message_builder)

    @provide
    def get_statistics_service(
        self,
        users_dao: UsersDAO,
        rides_dao: RidesDAO,
        bookings_dao: BookingsDAO,
        transactions_dao: TransactionsDAO,
    ) -> StatisticsService:
        return StatisticsService(users_dao, rides_dao, bookings_dao, transactions_dao)

    @provide
    def get_broadcast_service(self, bot: Bot, config: Config, users_dao: UsersDAO) -> BroadcastService:
        return BroadcastService(bot, config, users_dao)

    @provide
    def get_bot_service(self, bot: Bot, config: Config, users_dao: UsersDAO) -> BotService:
        return BotService(bot, config, users_dao)

    @provide
    def get_vip_service(
        self,
        settings_dao: SettingsDAO,
        users_dao: UsersDAO,
        transactions_dao: TransactionsDAO,
        bot_service: BotService,
        message_builder: MessageBuilder,
        cache: RedisService,
        cache_keys: CacheKeys,
    ) -> VipService:
        return VipService(
            settings_dao,
            users_dao,
            transactions_dao,
            bot_service,
            message_builder,
            cache,
            cache_keys,
        )


class UserAppProvider(Provider):
    scope = Scope.REQUEST

    @provide
    def create_or_get_user(
        self, users_dao: UsersDAO, bot_service: BotService, message_builder: MessageBuilder
    ) -> CreateOrGetUserInteractor:
        return CreateOrGetUserInteractor(users_dao, bot_service, message_builder)
