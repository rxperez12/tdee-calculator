from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tdee_calculator import clock
from tdee_calculator.calc import Site
from tdee_calculator.db import make_engine, run_migrations
from tdee_calculator.measurement_form import MeasurementInput
from tdee_calculator.measurements import (
    all_sessions,
    delete_session,
    get_session,
    upsert_session,
)
from tdee_calculator.models import MeasurementReading, MeasurementSession

DAY = date(2026, 10, 8)
MORNING = datetime(2026, 10, 8, 8)
EVENING = datetime(2026, 10, 8, 20)


@pytest.fixture
def session(config, monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: MORNING)
    run_migrations(config)
    engine = make_engine(config)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def stored(row):
    return {(r.site, r.reading): r.value_cm for r in row.readings}


def test_insert_and_query_order(session):
    assert all_sessions(session) == []
    assert get_session(session, DAY) is None
    upsert_session(session, MeasurementInput(DAY, {Site.NECK: (35.25, 36)}))
    upsert_session(
        session, MeasurementInput(DAY - timedelta(days=1), {Site.WAIST: (80,)})
    )
    session.expire_all()
    rows = all_sessions(session)
    assert [row.date for row in rows] == [DAY, DAY - timedelta(days=1)]
    assert stored(rows[0]) == {("neck", 1): 35.25, ("neck", 2): 36}
    assert rows[0].created_at == rows[0].updated_at == MORNING


@pytest.mark.parametrize(
    "readings,expected",
    [
        ({Site.NECK: (37, 38)}, {("neck", 1): 37, ("neck", 2): 38}),
        (
            {Site.NECK: (35.25, 36, 37)},
            {("neck", 1): 35.25, ("neck", 2): 36, ("neck", 3): 37},
        ),
        ({Site.NECK: (35.25,)}, {("neck", 1): 35.25}),
        (
            {Site.NECK: (35.25,), Site.HIP: (100,)},
            {("neck", 1): 35.25, ("hip", 1): 100},
        ),
    ],
)
def test_update_same_slots_add_remove_and_both(
    session, monkeypatch, readings, expected
):
    original = upsert_session(session, MeasurementInput(DAY, {Site.NECK: (35.25, 36)}))
    original_id = original.id
    first_slot_id = original.readings[0].id
    monkeypatch.setattr(clock, "now", lambda: EVENING)
    upsert_session(session, MeasurementInput(DAY, readings))
    session.expire_all()
    row = get_session(session, DAY)
    assert row.id == original_id
    assert next(r for r in row.readings if r.site == "neck").id == first_slot_id
    assert stored(row) == expected
    assert row.created_at == MORNING
    assert row.updated_at == EVENING
    assert session.scalar(select(func.count()).select_from(MeasurementSession)) == 1
    assert session.scalar(select(func.count()).select_from(MeasurementReading)) == len(
        expected
    )


def test_noop_preserves_timestamp_and_exact_values(session, monkeypatch):
    value = 39.37007874015748
    upsert_session(session, MeasurementInput(DAY, {Site.NECK: (value,)}))
    monkeypatch.setattr(clock, "now", lambda: EVENING)
    upsert_session(session, MeasurementInput(DAY, {Site.NECK: (value,)}))
    session.expire_all()
    row = get_session(session, DAY)
    assert stored(row) == {("neck", 1): value}
    assert row.updated_at == MORNING


def test_delete_cascades_and_missing_date_is_safe(session):
    upsert_session(session, MeasurementInput(DAY, {Site.NECK: (35, 36)}))
    assert delete_session(session, DAY)
    assert get_session(session, DAY) is None
    assert session.scalar(select(func.count()).select_from(MeasurementReading)) == 0
    assert not delete_session(session, DAY)


@pytest.mark.parametrize("duplicate", ["date", "slot"])
def test_unique_constraints_and_rollback_preserve_saved_data(session, duplicate):
    row = upsert_session(session, MeasurementInput(DAY, {Site.NECK: (35,)}))
    if duplicate == "date":
        session.add(MeasurementSession(date=DAY))
    else:
        row.readings.append(MeasurementReading(site="neck", reading=1, value_cm=40))
    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        session.commit()
    session.rollback()
    assert stored(get_session(session, DAY)) == {("neck", 1): 35}
