"""Storage for dated tape-measurement sessions in canonical centimetres."""

from datetime import date as Date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from tdee_calculator import clock
from tdee_calculator.measurement_form import MeasurementInput
from tdee_calculator.models import MeasurementReading, MeasurementSession


def get_session(session: Session, day: Date) -> MeasurementSession | None:
    return session.scalar(
        select(MeasurementSession)
        .where(MeasurementSession.date == day)
        .options(selectinload(MeasurementSession.readings))
    )


def upsert_session(session: Session, data: MeasurementInput) -> MeasurementSession:
    row = get_session(session, data.date)
    if row is None:
        row = MeasurementSession(date=data.date)
        session.add(row)
    existing = {(reading.site, reading.reading): reading for reading in row.readings}
    submitted = {
        (site.value, slot): value
        for site, values in data.readings.items()
        for slot, value in enumerate(values, start=1)
    }
    changed = False
    for key, value in submitted.items():
        reading = existing.get(key)
        if reading is None:
            row.readings.append(
                MeasurementReading(site=key[0], reading=key[1], value_cm=value)
            )
            changed = True
        elif reading.value_cm != value:
            reading.value_cm = value
            changed = True
    for key, reading in existing.items():
        if key not in submitted:
            row.readings.remove(reading)
            changed = True
    if changed:
        row.updated_at = clock.now()
    session.commit()
    return row


def delete_session(session: Session, day: Date) -> bool:
    row = get_session(session, day)
    if row is None:
        return False
    session.delete(row)
    session.commit()
    return True


def all_sessions(session: Session) -> list[MeasurementSession]:
    return list(
        session.scalars(
            select(MeasurementSession)
            .order_by(MeasurementSession.date.desc())
            .options(selectinload(MeasurementSession.readings))
        )
    )
