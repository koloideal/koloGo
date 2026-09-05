from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, Numeric, String, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from .booking import Booking
    from .transaction import Transaction

from .base import Base


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, unique=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal(0))
    registration_date: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_vip: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    bookings: Mapped[list[Booking]] = relationship("Booking", back_populates="user")
    transactions: Mapped[list[Transaction]] = relationship("Transaction", back_populates="user")

    def __repr__(self) -> str:
        return f"<User(user_id={self.user_id}, username='{self.username}', balance={self.balance})>"
