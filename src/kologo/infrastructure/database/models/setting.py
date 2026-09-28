from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
