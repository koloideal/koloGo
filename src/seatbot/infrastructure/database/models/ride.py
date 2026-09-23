from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, Float, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from .booking import Booking

from .base import Base


class Ride(Base):
    __tablename__ = "rides"

    departure_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal(0))
    seats_total: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    auto_approve: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", server_default="open")
    note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    origin: Mapped[str] = mapped_column(String(128), nullable=False)
    destination: Mapped[str] = mapped_column(String(128), nullable=False)
    remind_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30, server_default="30")
    remind_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    vip_hold_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    origin_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    origin_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    destination_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    destination_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    track_distance_m: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default="0")
    track_max_speed_mps: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default="0")
    live_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    live_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    arrive_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    awaiting_live_geo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    template_hidden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    bookings: Mapped[list[Booking]] = relationship("Booking", back_populates="ride")

    def __repr__(self) -> str:
        return f"<Ride(id={self.id}, departure_at={self.departure_at}, status={self.status})>"
