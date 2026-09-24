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
from seatbot.application.services.location import LocationService
from seatbot.application.services.payment import PaymentService
from seatbot.application.services.ride import RideService
from seatbot.application.services.statistics import StatisticsService
from seatbot.application.services.tracking import TrackingService
from seatbot.application.services.user import UserService
from seatbot.application.services.vip import VipService
from seatbot.infrastructure.cache import CacheKeys, RedisService
from seatbot.infrastructure.config.app import AppConfig
from seatbot.infrastructure.config.models import Config, GeoConfig, TrackingConfig
from seatbot.infrastructure.database.config import new_session_maker
from seatbot.infrastructure.database.dao import (BookingsDAO, LocationsDAO, RequisitesDAO,
                                                 RidesDAO, SettingsDAO, TrackPointsDAO,
                                                 TransactionsDAO, UsersDAO)
from seatbot.infrastructure.geo import GeoService
from seatbot.infrastructure.notifications import MessageBuilder
from seatbot.infrastructure.payments import CryptoBotPaymentService
from seatbot.infrastructure.post_commit import PostCommit
from seatbot.infrastructure.scheduling.payment_poller import PaymentStatusPoller
from seatbot.infrastructure.scheduling.tasks import (auto_close_past_rides,
                                                     auto_complete_stale_rides,
                                                     finish_stale_arrivals,
                                                     send_ride_reminders)
from seatbot.infrastructure.time import LocalClock


class DatabaseProvider(Provider):
    scope = Scope.REQUEST

    @provide(scope=Scope.APP)
    def get_session_maker(self, config: Config) -> async_sessionmaker[AsyncSession]:
        return new_session_maker(config.postgres.dsn)

    @provide
    async def get_post_commit(self) -> AsyncIterable[PostCommit]:
        post_commit = PostCommit()
        yield post_commit
        await post_commit.run()

    @provide
    async def get_session(
        self, session_maker: async_sessionmaker[AsyncSession], post_commit: PostCommit
    ) -> AsyncIterable[AsyncSession]:
        # зависимость от post_commit гарантирует порядок финализации: сначала коммит, потом post-commit
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

    @provide
    def get_locations_dao(self, session: AsyncSession) -> LocationsDAO:
        return LocationsDAO(session)

    @provide
    def get_track_points_dao(self, session: AsyncSession) -> TrackPointsDAO:
        return TrackPointsDAO(session)


class RedisProvider(Provider):
    scope = Scope.APP

    @provide
    async def get_redis(self, config: Config, app_config: AppConfig) -> AsyncIterable[Redis]:
        redis: Redis = Redis.from_url(
            config.redis.cache_dsn,
            decode_responses=True,
            max_connections=app_config.redis_max_connections,
        )
        try:
            yield redis
        finally:
            await redis.aclose()

    @provide(scope=Scope.REQUEST)
    def get_cache_service(self, redis: Redis, post_commit: PostCommit) -> RedisService:
        return RedisService(redis, post_commit)

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
        scheduler.add_job(
            func=auto_complete_stale_rides,
            trigger=IntervalTrigger(minutes=10),
            kwargs={"container": async_container},
            name="auto_complete_stale_rides",
        )
        scheduler.add_job(
            func=finish_stale_arrivals,
            trigger=IntervalTrigger(seconds=30),
            kwargs={"container": async_container},
            name="finish_stale_arrivals",
        )
        return scheduler

    @provide(scope=Scope.APP)
    def get_payment_poller(
        self, scheduler: AsyncIOScheduler, async_container: AsyncContainer
    ) -> PaymentStatusPoller:
        return PaymentStatusPoller(scheduler, async_container)


class ServicesProvider(Provider):
    scope = Scope.REQUEST

    @provide(scope=Scope.APP)
    def get_geo_config(self, config: Config) -> GeoConfig:
        return config.geo

    @provide(scope=Scope.APP)
    def get_tracking_config(self, config: Config) -> TrackingConfig:
        return config.tracking

    @provide(scope=Scope.APP)
    def get_geo_service(self, geo_config: GeoConfig, app_config: AppConfig) -> GeoService:
        return GeoService(geo_config, app_config)

    @provide
    def get_message_builder(self, clock: LocalClock, app_config: AppConfig) -> MessageBuilder:
        return MessageBuilder(clock, app_config)

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
        track_dao: TrackPointsDAO,
        bot_service: BotService,
        message_builder: MessageBuilder,
        clock: LocalClock,
        geo: GeoService,
        cache: RedisService,
        cache_keys: CacheKeys,
        app_config: AppConfig,
    ) -> RideService:
        return RideService(
            rides_dao,
            bookings_dao,
            users_dao,
            transactions_dao,
            track_dao,
            bot_service,
            message_builder,
            clock,
            geo,
            cache,
            cache_keys,
            app_config,
        )

    @provide
    def get_location_service(
        self, cache: RedisService, cache_keys: CacheKeys, locations_dao: LocationsDAO
    ) -> LocationService:
        return LocationService(cache, cache_keys, locations_dao)

    @provide
    def get_deposit_service(
        self,
        users_dao: UsersDAO,
        transactions_dao: TransactionsDAO,
        bot_service: BotService,
        message_builder: MessageBuilder,
        cache: RedisService,
        cache_keys: CacheKeys,
    ) -> DepositService:
        return DepositService(users_dao, transactions_dao, bot_service, message_builder, cache, cache_keys)

    @provide
    def get_statistics_service(
        self,
        users_dao: UsersDAO,
        rides_dao: RidesDAO,
        bookings_dao: BookingsDAO,
        transactions_dao: TransactionsDAO,
        cache: RedisService,
        cache_keys: CacheKeys,
    ) -> StatisticsService:
        return StatisticsService(users_dao, rides_dao, bookings_dao, transactions_dao, cache, cache_keys)

    @provide
    def get_broadcast_service(self, bot: Bot, config: Config, users_dao: UsersDAO) -> BroadcastService:
        return BroadcastService(bot, config, users_dao)

    @provide
    def get_bot_service(
        self, bot: Bot, config: Config, users_dao: UsersDAO, post_commit: PostCommit
    ) -> BotService:
        return BotService(bot, config, users_dao, post_commit)

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
        app_config: AppConfig,
    ) -> VipService:
        return VipService(
            settings_dao,
            users_dao,
            transactions_dao,
            bot_service,
            message_builder,
            cache,
            cache_keys,
            app_config,
        )

    @provide(scope=Scope.APP)
    def get_cryptobot_service(self, config: Config) -> CryptoBotPaymentService:
        return CryptoBotPaymentService(config.cryptobot)

    @provide
    def get_payment_service(
        self,
        transactions_dao: TransactionsDAO,
        settings_dao: SettingsDAO,
        cryptobot_service: CryptoBotPaymentService,
        poller: PaymentStatusPoller,
        users_dao: UsersDAO,
        message_builder: MessageBuilder,
        cache: RedisService,
        cache_keys: CacheKeys,
        bot_service: BotService,
        clock: LocalClock,
        app_config: AppConfig,
    ) -> PaymentService:
        return PaymentService(
            transactions_dao,
            settings_dao,
            cryptobot_service,
            poller,
            users_dao,
            message_builder,
            cache,
            cache_keys,
            bot_service,
            clock,
            app_config,
        )

    @provide
    def get_tracking_service(
        self,
        rides_dao: RidesDAO,
        bookings_dao: BookingsDAO,
        track_dao: TrackPointsDAO,
        ride_service: RideService,
        bot_service: BotService,
        message_builder: MessageBuilder,
        clock: LocalClock,
        geo: GeoService,
        tracking_config: TrackingConfig,
    ) -> TrackingService:
        return TrackingService(
            rides_dao,
            bookings_dao,
            track_dao,
            ride_service,
            bot_service,
            message_builder,
            clock,
            geo,
            tracking_config,
        )


class UserAppProvider(Provider):
    scope = Scope.REQUEST

    @provide
    def create_or_get_user(
        self,
        users_dao: UsersDAO,
        bot_service: BotService,
        message_builder: MessageBuilder,
        cache: RedisService,
        cache_keys: CacheKeys,
    ) -> CreateOrGetUserInteractor:
        return CreateOrGetUserInteractor(users_dao, bot_service, message_builder, cache, cache_keys)
