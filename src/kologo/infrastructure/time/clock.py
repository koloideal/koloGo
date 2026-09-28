from datetime import UTC, datetime
from zoneinfo import ZoneInfo


class LocalClock:
    def __init__(self, tz: ZoneInfo) -> None:
        self.tz = tz

    def now(self) -> datetime:
        return datetime.now(UTC)

    def to_local(self, dt: datetime) -> datetime:
        return dt.astimezone(self.tz)

    def to_utc(self, dt: datetime) -> datetime:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=self.tz)
        return dt.astimezone(UTC)

    def fmt(self, dt: datetime, fmt: str = "%d.%m.%Y %H:%M") -> str:
        return dt.astimezone(self.tz).strftime(fmt)

    def local_dt(
        self,
        year: int,
        month: int,
        day: int,
        hour: int,
        minute: int = 0,
        second: int = 0,
    ) -> datetime:
        return self.to_utc(datetime(year, month, day, hour, minute, second, tzinfo=self.tz))
