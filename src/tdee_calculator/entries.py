from datetime import date as Date

from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tdee_calculator.calc import DayLog
from tdee_calculator.db import claim_version
from tdee_calculator.entry_form import EntryInput
from tdee_calculator.models import Entry

RECENT_LIMIT = 30


def get_entry(session: Session, entry_date: Date) -> Entry | None:
    return session.get(Entry, entry_date)


def upsert_entry(session: Session, data: EntryInput) -> Entry:
    entry = get_entry(session, data.date)
    if entry is None:
        entry = Entry(date=data.date)
        session.add(entry)
    entry.weight_kg = data.weight_kg
    entry.calories = data.calories
    entry.source = "manual"
    session.commit()
    return entry


def upsert_entry_if_unchanged(
    session: Session, data: EntryInput, expected_version: str
) -> Entry | None:
    """Save only if `data.date`'s entry is still `expected_version` ("" for none).

    Returns None, saving nothing, when another save got there first.
    """
    if expected_version:
        if not claim_version(session, Entry, data.date, expected_version):
            session.rollback()
            return None
    else:
        try:
            session.connection().execute(insert(Entry).values(date=data.date))
        except IntegrityError:
            session.rollback()
            return None
    return upsert_entry(session, data)


def delete_entry(session: Session, entry_date: Date) -> bool:
    entry = get_entry(session, entry_date)
    if entry is None:
        return False
    session.delete(entry)
    session.commit()
    return True


def recent_entries(session: Session, limit: int = RECENT_LIMIT) -> list[Entry]:
    return list(session.scalars(select(Entry).order_by(Entry.date.desc()).limit(limit)))


def count_entries(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Entry)) or 0


def all_entries(session: Session) -> list[Entry]:
    """Every entry, oldest first."""
    return list(session.scalars(select(Entry).order_by(Entry.date)))


def all_day_logs(session: Session) -> list[DayLog]:
    """Every entry as calc input, oldest first."""
    return [
        DayLog(entry.date, entry.weight_kg, entry.calories)
        for entry in all_entries(session)
    ]
