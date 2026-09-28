from datetime import datetime, timedelta

from kologo.application.services.bot import BotService
from kologo.application.services.ride import RideService
from kologo.domain.schemas import BookingStatus, Ride, RideStatus
from kologo.infrastructure.config.models import TrackingConfig
from kologo.infrastructure.database.dao import BookingsDAO, RidesDAO, TrackPointsDAO
from kologo.infrastructure.database.models import Ride as OrmRide
from kologo.infrastructure.geo import GeoService
from kologo.infrastructure.notifications import MessageBuilder
from kologo.infrastructure.time import LocalClock


class TrackingService:
    def __init__(
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
    ) -> None:
        self._rides_dao = rides_dao
        self._bookings_dao = bookings_dao
        self._track_dao = track_dao
        self._ride_service = ride_service
        self._bot_service = bot_service
        self._messages = message_builder
        self._clock = clock
        self._geo = geo
        self._tracking = tracking_config

    async def request_start(self, ride_id: int) -> Ride | None:
        ride = await self._rides_dao.get_by_id_for_update(ride_id)
        if not ride or ride.status not in (RideStatus.OPEN, RideStatus.CLOSED):
            return None
        await self._rides_dao.clear_awaiting_live()
        await self._rides_dao.set_awaiting_live(ride_id, True)
        return ride

    async def handle_live_start(self, chat_id: int, message_id: int, lat: float, lon: float) -> Ride | None:
        orm = await self._rides_dao.get_awaiting_live_orm()
        if not orm:
            return None
        orm.awaiting_live_geo = False
        orm.status = RideStatus.IN_PROGRESS.value
        orm.started_at = self._clock.now()
        orm.live_chat_id = chat_id
        orm.live_message_id = message_id
        orm.arrive_streak = 0
        await self._track_dao.add_point(orm.id, 0, lat, lon)
        await self._ride_service.invalidate_ride(orm.id)
        ride = await self._rides_dao.get_by_id(orm.id)
        if ride:
            approved = await self._bookings_dao.list_for_ride_with_status(
                ride.ride_id, {BookingStatus.APPROVED}
            )
            for booking in approved:
                await self._bot_service.notify_user(
                    booking.user_id,
                    self._messages.driver_departed_notification(ride),
                    reply_markup=self._messages.origin_keyboard(ride),
                )
        return ride

    async def handle_update(
        self,
        chat_id: int,
        message_id: int,
        lat: float,
        lon: float,
        live_period: int | None,
        horizontal_accuracy: float | None,
    ) -> None:
        orm = await self._rides_dao.get_tracking_orm(chat_id, message_id)
        if not orm:
            return

        accurate = horizontal_accuracy is None or horizontal_accuracy <= self._tracking.max_accuracy_m
        if accurate:
            last = await self._track_dao.last_point(orm.id)
            await self._record_point(orm, last, lat, lon)
            self._update_arrival(orm, last, lat, lon)

        if live_period is None:
            if orm.arrive_streak > 0:
                await self.arrive(orm.id)
                return
            orm.live_chat_id = None
            orm.live_message_id = None
            await self._bot_service.send_log_to_admin(
                self._messages.tracking_stopped_admin_log(
                    orm.id, self._distance_to_destination(orm, lat, lon)
                )
            )
            return

        if orm.arrive_streak >= self._tracking.arrival_debounce:
            await self.arrive(orm.id)

    async def _record_point(
        self, orm: OrmRide, last: tuple[float, float, datetime] | None, lat: float, lon: float
    ) -> None:
        seq = await self._track_dao.count_for_ride(orm.id)
        if last is None:
            await self._track_dao.add_point(orm.id, seq, lat, lon)
            return
        gap = self._geo.haversine_m(last[0], last[1], lat, lon)
        dt = (self._clock.now() - last[2]).total_seconds()
        if gap < self._tracking.min_point_gap_m or (dt > 0 and gap / dt > self._tracking.max_speed_mps):
            return
        orm.track_distance_m += gap
        if dt > 0:
            orm.track_max_speed_mps = max(orm.track_max_speed_mps, gap / dt)
        await self._track_dao.add_point(orm.id, seq, lat, lon)

    def _distance_to_destination(self, orm: OrmRide, lat: float, lon: float) -> float | None:
        if orm.destination_lat is None or orm.destination_lon is None:
            return None
        return self._geo.haversine_m(lat, lon, orm.destination_lat, orm.destination_lon)

    def _update_arrival(
        self, orm: OrmRide, last: tuple[float, float, datetime] | None, lat: float, lon: float
    ) -> None:
        if orm.destination_lat is None or orm.destination_lon is None:
            return
        destination = (orm.destination_lat, orm.destination_lon)
        if last is None:
            dist = self._geo.haversine_m(lat, lon, *destination)
        else:
            dist = self._geo.segment_distance_m((last[0], last[1]), (lat, lon), destination)
        if dist <= self._tracking.arrival_radius_m:
            orm.arrive_streak += 1
        else:
            orm.arrive_streak = 0

    async def finish_stale_arrivals(self) -> int:
        finished = 0
        threshold = self._clock.now() - timedelta(seconds=self._tracking.arrival_dwell_s)
        for ride_id in await self._rides_dao.list_arriving_ids():
            last = await self._track_dao.last_point(ride_id)
            if (last is None or last[2] <= threshold) and await self.arrive(ride_id):
                finished += 1
        return finished

    async def arrive(self, ride_id: int) -> Ride | None:
        return await self._ride_service.complete_ride(ride_id)
