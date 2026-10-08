from datetime import date as Date
from datetime import datetime as DateTime

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from tdee_calculator import clock


def _now() -> DateTime:
    return clock.now()


class Base(DeclarativeBase):
    pass


class Entry(Base):
    __tablename__ = "entries"

    date: Mapped[Date] = mapped_column(primary_key=True)
    weight_kg: Mapped[float | None]
    calories: Mapped[int | None]
    source: Mapped[str] = mapped_column(default="manual", server_default="manual")
    created_at: Mapped[DateTime] = mapped_column(default=_now)
    updated_at: Mapped[DateTime] = mapped_column(default=_now, onupdate=_now)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str]
