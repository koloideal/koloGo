from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from .ride import Ride
    from .user import User

from .base import Base


class Booking(Base):
    __tablename__ = "bookings"

    ride_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("rides.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    paid_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal(0), server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    ride: Mapped[Ride] = relationship("Ride", back_populates="bookings")
    user: Mapped[User] = relationship("User", back_populates="bookings")

    def __repr__(self) -> str:
        return (
            f"<Booking(id={self.id}, ride_id={self.ride_id}, user_id={self.user_id}, status={self.status})>"
        )
