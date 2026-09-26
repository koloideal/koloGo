from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from seatbot.application.services.ride import RideService
from seatbot.infrastructure.cache import CacheKeys
from seatbot.infrastructure.config.app import AppConfig
from seatbot.infrastructure.config.models import GeoConfig
from seatbot.infrastructure.geo import GeoService
from seatbot.infrastructure.notifications import MessageBuilder
from seatbot.infrastructure.time import LocalClock
from tests.fakes import (FakeBookingsDAO, FakeBotService, FakeCache, FakeRidesDAO,
                         FakeTrackPointsDAO, FakeTransactionsDAO, FakeUsersDAO)


@pytest.fixture
def clock() -> LocalClock:
    return LocalClock(ZoneInfo("Europe/Minsk"))


@pytest.fixture
def messages(clock: LocalClock) -> MessageBuilder:
    return MessageBuilder(clock, AppConfig())


@pytest.fixture
def geo() -> GeoService:
    return GeoService(GeoConfig(yandex_max_route_points=20), AppConfig())


class ServiceFixture:
    def __init__(self, clock: LocalClock) -> None:
        self.bookings = FakeBookingsDAO()
        self.rides = FakeRidesDAO(self.bookings)
        self.users = FakeUsersDAO()
        self.transactions = FakeTransactionsDAO()
        self.track = FakeTrackPointsDAO()
        self.bot = FakeBotService()
        self.cache = FakeCache()
        self.service = RideService(
            rides_dao=self.rides,
            bookings_dao=self.bookings,
            users_dao=self.users,
            transactions_dao=self.transactions,
            track_dao=self.track,
            bot_service=self.bot,
            message_builder=MessageBuilder(clock, AppConfig()),
            clock=clock,
            geo=GeoService(GeoConfig(), AppConfig()),
            cache=self.cache,
            cache_keys=CacheKeys(),
            app_config=AppConfig(),
        )


@pytest.fixture
def fx(clock: LocalClock) -> ServiceFixture:
    return ServiceFixture(clock)


@pytest.fixture
def utc_now() -> datetime:
    return datetime.now(UTC)
