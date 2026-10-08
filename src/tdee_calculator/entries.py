from datetime import date as Date

from sqlalchemy import select
from sqlalchemy.orm import Session

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


def delete_entry(session: Session, entry_date: Date) -> bool:
    entry = get_entry(session, entry_date)
    if entry is None:
        return False
    session.delete(entry)
    session.commit()
    return True


def recent_entries(session: Session, limit: int = RECENT_LIMIT) -> list[Entry]:
    return list(session.scalars(select(Entry).order_by(Entry.date.desc()).limit(limit)))
