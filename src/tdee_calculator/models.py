from datetime import date as Date
from datetime import datetime as DateTime

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

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


class MeasurementSession(Base):
    __tablename__ = "measurement_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[Date] = mapped_column(unique=True)
    created_at: Mapped[DateTime] = mapped_column(default=_now)
    updated_at: Mapped[DateTime] = mapped_column(default=_now, onupdate=_now)
    readings: Mapped[list["MeasurementReading"]] = relationship(
        cascade="all, delete-orphan",
        order_by=lambda: (MeasurementReading.site, MeasurementReading.reading),
    )


class MeasurementReading(Base):
    __tablename__ = "measurement_readings"
    __table_args__ = (UniqueConstraint("session_id", "site", "reading"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("measurement_sessions.id"))
    site: Mapped[str]
    reading: Mapped[int]
    value_cm: Mapped[float]
