from seatbot.application.services.bot import BotService
from seatbot.application.services.ride import RideService
from seatbot.domain.schemas import BookingStatus, Ride, RideStatus
from seatbot.infrastructure.config.models import TrackingConfig
from seatbot.infrastructure.database.dao import BookingsDAO, RidesDAO, TrackPointsDAO
from seatbot.infrastructure.geo import GeoService
from seatbot.infrastructure.notifications import MessageBuilder
from seatbot.infrastructure.time import LocalClock


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
        return await self._rides_dao.get_by_id(orm.id)

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

        if live_period is None:
            orm.live_chat_id = None
            orm.live_message_id = None
            await self._bot_service.send_log_to_admin(self._messages.tracking_stopped_admin_log(orm.id))
            return

        if horizontal_accuracy is not None and horizontal_accuracy > self._tracking.max_accuracy_m:
            return

        seq = await self._track_dao.count_for_ride(orm.id)
        last = await self._track_dao.last_point(orm.id)
        now = self._clock.now()
        if last is not None:
            gap = self._geo.haversine_m(last[0], last[1], lat, lon)
            dt = (now - last[2]).total_seconds()
            if gap >= self._tracking.min_point_gap_m and not (
                0 < dt and gap / dt > self._tracking.max_speed_mps
            ):
                orm.track_distance_m += gap
                if dt > 0:
                    orm.track_max_speed_mps = max(orm.track_max_speed_mps, gap / dt)
                await self._track_dao.add_point(orm.id, seq, lat, lon)
        else:
            await self._track_dao.add_point(orm.id, seq, lat, lon)

        if orm.destination_lat is None or orm.destination_lon is None:
            return
        dist = self._geo.haversine_m(lat, lon, orm.destination_lat, orm.destination_lon)
        if dist <= self._tracking.arrival_radius_m:
            orm.arrive_streak += 1
        else:
            orm.arrive_streak = 0
        if orm.arrive_streak >= self._tracking.arrival_debounce:
            await self._arrive(orm.id)

    async def _arrive(self, ride_id: int) -> None:
        await self._rides_dao.set_finished_at(ride_id, self._clock.now())
        await self._ride_service.complete_ride(ride_id)
        ride = await self._rides_dao.get_by_id(ride_id)
        if not ride:
            return
        points = await self._track_dao.list_for_ride(ride_id)
        stats_text = self._messages.ride_arrived_notification(ride)
        map_url = self._geo.yandex_route_url(points) if len(points) >= 2 else None
        map_markup = self._messages.ride_map_keyboard(map_url) if map_url else None
        approved = await self._bookings_dao.list_for_ride_with_status(ride_id, {BookingStatus.COMPLETED})
        for booking in approved:
            await self._bot_service.notify_user(booking.user_id, stats_text, reply_markup=map_markup)
