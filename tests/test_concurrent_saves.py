"""Saves that land between a route's version check and its write.

Two tabs submitting at once can interleave this way for real. To make the timing
deterministic, these tests wrap the route's edit_conflict check so a second
connection commits its change right after the check passes.
"""

from collections.abc import Callable
from datetime import date, datetime

import pytest
from sqlalchemy.orm import Session
from test_app import FormInputs, stored_entries
from test_home_measurement_routes import assert_home_feedback, home_form
from test_measurement_routes import form, readings

from tdee_calculator import clock, entries, measurements
from tdee_calculator.calc import Site
from tdee_calculator.db import make_engine
from tdee_calculator.entry_form import EntryInput
from tdee_calculator.measurement_form import MeasurementInput
from tdee_calculator.routes import measurements as measurement_routes
from tdee_calculator.routes import today as today_routes

DAY = date(2026, 10, 8)
LATER = datetime(2026, 10, 8, 9)


def after_check(monkeypatch, config, route_module, change: Callable[[Session], object]):
    """Commit `change` from another connection right after the first check."""
    check = route_module.edit_conflict
    pending = [change]

    def check_then_interleave(*args):
        result = check(*args)
        if pending:
            monkeypatch.setattr(clock, "now", lambda: LATER)
            engine = make_engine(config)
            try:
                with Session(engine) as other:
                    pending.pop()(other)
            finally:
                engine.dispose()
        return result

    monkeypatch.setattr(route_module, "edit_conflict", check_then_interleave)


def entry_form(client, day="2026-10-08", **changes):
    values = FormInputs(
        client.get("/", params={"date": day}).text, action="/entries"
    ).values
    return {**values, **changes}


def post_entry(client, values):
    return client.post("/entries", data=values, follow_redirects=False)


@pytest.mark.parametrize("existing", [True, False])
def test_entry_save_refused_when_another_save_lands_first(
    client, config, monkeypatch, existing
):
    if existing:
        assert post_entry(client, entry_form(client, weight="80")).status_code == 303
    values = entry_form(client, weight="90")
    after_check(
        monkeypatch,
        config,
        today_routes,
        lambda other: entries.upsert_entry(other, EntryInput(DAY, 85, None)),
    )

    response = post_entry(client, values)

    assert response.status_code == 409
    assert "8 Oct changed since this page loaded" in response.text
    assert stored_entries(config) == [("2026-10-08", 85, None, "manual")]


def test_entry_save_refused_when_entry_is_deleted_first(client, config, monkeypatch):
    assert post_entry(client, entry_form(client, weight="80")).status_code == 303
    values = entry_form(client, weight="90")
    after_check(
        monkeypatch,
        config,
        today_routes,
        lambda other: entries.delete_entry(other, DAY),
    )

    response = post_entry(client, values)

    assert response.status_code == 409
    assert "8 Oct changed since this page loaded" in response.text
    assert stored_entries(config) == []


def test_entry_moved_to_a_date_another_save_just_filled(client, config, monkeypatch):
    values = entry_form(client, "2026-10-07", entry_date="2026-10-08", weight="90")
    after_check(
        monkeypatch,
        config,
        today_routes,
        lambda other: entries.upsert_entry(other, EntryInput(DAY, 85, None)),
    )

    response = post_entry(client, values)

    assert response.status_code == 409
    assert "Thu 8 Oct already has saved data" in response.text
    assert stored_entries(config) == [("2026-10-08", 85, None, "manual")]


def post_measurements(client, values):
    return client.post("/measurements", data=values, follow_redirects=False)


@pytest.mark.parametrize("existing", [True, False])
@pytest.mark.parametrize("source", ["home", "measurements"])
@pytest.mark.usefixtures("measurement_profile")
def test_measurement_save_refused_when_another_save_lands_first(
    client, config, monkeypatch, existing, source
):
    if existing:
        values = {**form(client), "neck_1": "35"}
        assert post_measurements(client, values).status_code == 303
    values = {
        **(home_form(client) if source == "home" else form(client)),
        "neck_1": "40",
    }
    after_check(
        monkeypatch,
        config,
        measurement_routes,
        lambda other: measurements.upsert_session(
            other, MeasurementInput(DAY, {Site.NECK: (37,)})
        ),
    )

    response = post_measurements(client, values)

    assert response.status_code == 409
    if source == "home":
        assert_home_feedback(response)
    assert "Reload this session" in response.text
    assert readings(config) == [("neck", 1, 37)]


@pytest.mark.parametrize("source", ["home", "measurements"])
@pytest.mark.usefixtures("measurement_profile")
def test_measurement_save_refused_when_session_is_deleted_first(
    client, config, monkeypatch, source
):
    assert (
        post_measurements(client, {**form(client), "neck_1": "35"}).status_code == 303
    )
    values = {
        **(home_form(client) if source == "home" else form(client)),
        "neck_1": "40",
    }
    after_check(
        monkeypatch,
        config,
        measurement_routes,
        lambda other: measurements.delete_session(other, DAY),
    )

    response = post_measurements(client, values)

    assert response.status_code == 409
    if source == "home":
        assert_home_feedback(response)
    assert "Reload this session" in response.text
    assert readings(config) == []


@pytest.mark.parametrize("source", ["home", "measurements"])
@pytest.mark.usefixtures("measurement_profile")
def test_measurements_moved_to_a_date_another_save_just_filled(
    client, config, monkeypatch, source
):
    values = {
        **(
            home_form(client, day="2026-10-07")
            if source == "home"
            else form(client, "2026-10-07")
        ),
        "date": "2026-10-08",
        "neck_1": "40",
    }
    after_check(
        monkeypatch,
        config,
        measurement_routes,
        lambda other: measurements.upsert_session(
            other, MeasurementInput(DAY, {Site.NECK: (37,)})
        ),
    )

    response = post_measurements(client, values)

    assert response.status_code == 409
    if source == "home":
        assert_home_feedback(response)
    assert "Edit this session" in response.text
    assert readings(config) == [("neck", 1, 37)]
