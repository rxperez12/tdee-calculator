from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from tdee_calculator import clock
from tdee_calculator.calc import DayLog
from tdee_calculator.db import make_engine, run_migrations
from tdee_calculator.entries import (
    all_day_logs,
    delete_entry,
    get_entry,
    recent_entries,
    upsert_entry,
)
from tdee_calculator.entry_form import EntryInput
from tdee_calculator.models import Entry

DAY = date(2026, 10, 8)


@pytest.fixture
def session(config, monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 10, 8, 8))
    run_migrations(config)
    engine = make_engine(config)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def test_insert_persists_manual_entry(session) -> None:
    upsert_entry(session, EntryInput(DAY, 80.25, 2000))
    session.expire_all()
    row = get_entry(session, DAY)
    assert row is not None
    assert row.weight_kg == pytest.approx(80.25, abs=1e-9)
    assert row.calories == 2000
    assert row.source == "manual"
    assert row.created_at == row.updated_at == datetime(2026, 10, 8, 8)
    assert get_entry(session, DAY - timedelta(days=1)) is None


def test_update_preserves_creation_time_and_one_row(session, monkeypatch) -> None:
    upsert_entry(session, EntryInput(DAY, 80.25, 2000))
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 10, 8, 20))
    upsert_entry(session, EntryInput(DAY, 81.0, 2100))
    session.expire_all()
    rows = list(session.scalars(select(Entry)))
    assert len(rows) == 1
    assert rows[0].weight_kg == pytest.approx(81.0, abs=1e-9)
    assert rows[0].calories == 2100
    assert rows[0].created_at == datetime(2026, 10, 8, 8)
    assert rows[0].updated_at == datetime(2026, 10, 8, 20)


def test_identical_save_keeps_timestamp(session, monkeypatch) -> None:
    upsert_entry(session, EntryInput(DAY, 80.25, 2000))
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 10, 8, 20))
    row = upsert_entry(session, EntryInput(DAY, 80.25, 2000))
    session.refresh(row)
    assert row.updated_at == datetime(2026, 10, 8, 8)


@pytest.mark.parametrize("weight,calories", [(None, 2000), (80.25, None)])
def test_replace_clears_blank_fields(session, weight, calories) -> None:
    upsert_entry(session, EntryInput(DAY, 80.25, 2000))
    row = upsert_entry(session, EntryInput(DAY, weight, calories))
    session.refresh(row)
    if weight is None:
        assert row.weight_kg is None
    else:
        assert row.weight_kg == pytest.approx(weight, abs=1e-9)
    assert row.calories == calories


def test_manual_save_claims_imported_row(session) -> None:
    session.add(Entry(date=DAY, weight_kg=80.0, source="spreadsheet"))
    session.commit()
    row = upsert_entry(session, EntryInput(DAY, 80.0, None))
    session.refresh(row)
    assert row.source == "manual"


def test_delete_existing_and_missing(session) -> None:
    upsert_entry(session, EntryInput(DAY, 80.0, None))
    assert delete_entry(session, DAY) is True
    assert get_entry(session, DAY) is None
    assert delete_entry(session, DAY) is False


def test_recent_entries_orders_and_limits(session) -> None:
    assert recent_entries(session) == []
    for offset in reversed(range(32)):
        upsert_entry(session, EntryInput(DAY - timedelta(days=offset), 80.0, None))
    assert [row.date for row in recent_entries(session, limit=2)] == [
        DAY,
        date(2026, 10, 7),
    ]
    assert len(recent_entries(session)) == 30


def test_all_day_logs_converts_rows_oldest_first(session) -> None:
    assert all_day_logs(session) == []
    upsert_entry(session, EntryInput(DAY, 80.25, None))
    upsert_entry(session, EntryInput(DAY - timedelta(days=2), None, 2000))
    upsert_entry(session, EntryInput(DAY - timedelta(days=1), 80.5, 2100))
    assert all_day_logs(session) == [
        DayLog(date(2026, 10, 6), None, 2000),
        DayLog(date(2026, 10, 7), 80.5, 2100),
        DayLog(DAY, 80.25, None),
    ]
