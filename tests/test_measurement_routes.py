from datetime import date, datetime
from html import unescape

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_app import FormInputs

from tdee_calculator import clock
from tdee_calculator.calc import Sex
from tdee_calculator.db import make_engine
from tdee_calculator.models import MeasurementReading, MeasurementSession
from tdee_calculator.settings import Settings, save_settings
from tdee_calculator.units import WeightUnit

DAY = date(2026, 10, 8)


def form(client, day="2026-10-08"):
    return FormInputs(
        client.get("/measurements", params={"date": day}).text,
        action="/measurements",
    ).values


def save(client, values, **changes):
    return client.post(
        "/measurements", data={**values, **changes}, follow_redirects=False
    )


def readings(config):
    engine = make_engine(config)
    try:
        with Session(engine) as session:
            return [
                (r.site, r.reading, r.value_cm)
                for r in session.scalars(
                    select(MeasurementReading).order_by(
                        MeasurementReading.site, MeasurementReading.reading
                    )
                )
            ]
    finally:
        engine.dispose()


def settings(config, *, sex=Sex.MALE, height=180.34, weight=WeightUnit.KG):
    engine = make_engine(config)
    try:
        with Session(engine) as session:
            save_settings(
                session, Settings(sex=sex, height_cm=height, weight_unit=weight)
            )
    finally:
        engine.dispose()


def test_empty_page_form_and_instructions(client):
    page = client.get("/measurements")
    assert page.status_code == 200
    assert 'aria-current="page">Measurements' in page.text
    assert "No measurements yet" in page.text
    assert '<details class="measurement-instructions" open>' in page.text
    inputs = FormInputs(page.text, action="/measurements")
    assert inputs.values["date"] == "2026-10-08"
    assert inputs.values["weight_unit"] == "kg"
    assert inputs.inputs["neck_1"]["min"] == "20.0"
    assert inputs.inputs["neck_1"]["step"] == "any"
    assert 'name="energy_unit"' not in page.text


@pytest.mark.parametrize("day", ["bad-date", "2026-10-09"])
def test_get_invalid_or_future_date_defaults_today(client, day):
    assert form(client, day)["date"] == "2026-10-08"


@pytest.mark.parametrize(
    "weight,text,expected",
    [(WeightUnit.KG, "39.37", 39.37), (WeightUnit.LB, "15.5", 39.37)],
)
def test_save_and_reload_canonical_readings(client, config, weight, text, expected):
    settings(config, weight=weight)
    response = save(
        client,
        form(client),
        neck_1=text,
        abdomen_3="34" if weight == WeightUnit.LB else "86.36",
    )
    assert response.status_code == 303
    assert (
        response.headers["location"] == "/measurements?date=2026-10-08&saved=2026-10-08"
    )
    assert readings(config) == [
        ("abdomen", 1, pytest.approx(86.36, abs=1e-9)),
        ("neck", 1, pytest.approx(expected, abs=1e-9)),
    ]
    assert (
        "Saved measurements for Thu 8 Oct"
        in client.get(response.headers["location"]).text
    )
    loaded = form(client)
    assert loaded["abdomen_3"] == ""
    assert loaded["loaded_version"]


@pytest.mark.parametrize("weight", list(WeightUnit))
def test_edit_without_drift_after_unit_switches(client, config, weight):
    settings(config, weight=weight)
    save(
        client,
        form(client),
        neck_1="15.512345" if weight == WeightUnit.LB else "39.3712345",
    )
    original = readings(config)
    for selected in (WeightUnit.LB, WeightUnit.KG, weight):
        settings(config, weight=selected)
        assert save(client, form(client)).status_code == 303
        assert readings(config) == original


def test_overwrite_guard_preserves_both_dates(client, config):
    save(client, form(client, "2026-10-07"), neck_1="35")
    response = save(client, form(client), date="2026-10-07", neck_1="40")
    assert response.status_code == 409
    assert "Edit this session" in response.text
    assert readings(config) == [("neck", 1, 35)]


def test_version_guard_refuses_stale_tab_and_deleted_session(
    client, config, monkeypatch
):
    save(client, form(client), neck_1="35")
    stale = form(client)
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 10, 8, 9))
    assert save(client, form(client), neck_1="36").status_code == 303
    response = save(client, stale, neck_1="37")
    assert response.status_code == 409
    assert "Reload this session" in response.text
    assert readings(config) == [("neck", 1, 36)]
    client.post("/measurements/2026-10-08/delete")
    assert save(client, stale, neck_1="38").status_code == 409
    assert readings(config) == []


def test_concurrent_creation_refuses_empty_form_from_other_tab(client, config):
    stale = form(client)
    save(client, form(client), neck_1="35")
    assert save(client, stale, neck_1="40").status_code == 409
    assert readings(config) == [("neck", 1, 35)]


def test_stale_units_refresh_without_echoing_submitted_values(client, config):
    stale = form(client)
    settings(config, weight=WeightUnit.LB)
    response = save(client, stale, neck_1="73.123456")
    assert response.status_code == 409
    assert "Your units changed" in response.text
    assert "73.123456" not in response.text
    assert form(client)["weight_unit"] == "lb"
    assert readings(config) == []


def test_energy_unit_change_does_not_block_measurements(client, config):
    stale = form(client)
    client.post("/settings/units", data={"weight_unit": "kg", "energy_unit": "kJ"})
    assert save(client, stale, neck_1="35").status_code == 303
    assert readings(config) == [("neck", 1, 35)]


@pytest.mark.parametrize(
    "changes",
    [{"neck_1": "nan"}, {"date": "bad"}, {"date": "2026-10-09"}, {"neck_1": ""}],
)
def test_invalid_submission_keeps_typed_values_and_saved_rows(client, config, changes):
    save(client, form(client), neck_1="35")
    response = save(client, form(client), **changes)
    assert response.status_code == 422
    assert readings(config) == [("neck", 1, 35)]
    returned = FormInputs(response.text, action="/measurements").values
    for field, value in changes.items():
        assert returned[field] == value


def test_missing_loaded_date_still_guards_existing_session(client, config):
    save(client, form(client), neck_1="35")
    assert (
        save(client, form(client), loaded_date="invalid", neck_1="40").status_code
        == 409
    )
    assert readings(config) == [("neck", 1, 35)]


def test_new_date_can_be_saved_from_loaded_existing_session(client, config):
    save(client, form(client, "2026-10-07"), neck_1="35")
    assert (
        save(
            client, form(client, "2026-10-07"), date="2026-10-08", neck_1="40"
        ).status_code
        == 303
    )
    engine = make_engine(config)
    try:
        with Session(engine) as session:
            assert len(list(session.scalars(select(MeasurementSession)))) == 2
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "sex,height,reason",
    [
        (None, None, "Set sex and height"),
        (None, 180, "Set sex"),
        (Sex.MALE, None, "Set height"),
    ],
)
def test_settings_needed_but_raw_readings_remain_visible(
    client, config, sex, height, reason
):
    settings(config, sex=sex, height=height)
    save(client, form(client), neck_1="35")
    page = client.get("/measurements").text
    assert reason in page
    assert '<a href="/settings">' in page
    assert "35.0" in page


@pytest.mark.parametrize(
    "sex,values,expected",
    [
        (Sex.MALE, {"neck_1": "39.37", "abdomen_1": "88.9"}, "18%"),
        (Sex.FEMALE, {"neck_1": "33.02", "waist_1": "71.12", "hip_1": "96.52"}, "26%"),
    ],
)
def test_estimates_for_both_equations(client, config, sex, values, expected):
    settings(config, sex=sex, height=180.34 if sex == Sex.MALE else 165.1)
    save(client, form(client), **values)
    page = client.get("/measurements").text
    assert expected in page
    assert 'measured <time datetime="2026-10-08">Thu 8 Oct' in page


@pytest.mark.parametrize(
    "values",
    [
        {"neck_1": "40", "abdomen_1": "40"},
        {"neck_1": "40", "abdomen_1": "40.1"},
        {"neck_1": "20", "abdomen_1": "250"},
    ],
)
def test_out_of_range_keeps_saved_readings(client, config, values):
    settings(config)
    assert save(client, form(client), **values).status_code == 303
    assert "Outside the equation's range" in unescape(client.get("/measurements").text)
    assert len(readings(config)) == 2


def test_latest_valid_estimate_retains_its_date_after_newer_partial_session(
    client, config
):
    settings(config)
    save(client, form(client, "2026-10-07"), neck_1="39.37", abdomen_1="88.9")
    save(client, form(client), waist_1="80")
    page = client.get("/measurements").text
    hero = page.split('aria-labelledby="estimate-heading">')[1].split("</section>")[0]
    assert "18%" in hero
    assert 'measured <time datetime="2026-10-07">Wed 7 Oct' in hero
    assert "Newer measurements on Thu 8 Oct: Needs neck and abdomen" in " ".join(
        hero.split()
    )
    assert '<details class="measurement-instructions" >' in page
    # Removing the valid session leaves the newer session's missing-input reason.
    assert (
        client.post(
            "/measurements/2026-10-07/delete", follow_redirects=False
        ).status_code
        == 303
    )
    assert "Needs neck and abdomen" in client.get("/measurements").text


def test_history_uses_means_and_current_settings(client, config):
    settings(config)
    save(
        client,
        form(client),
        neck_1="39.37",
        abdomen_1="86.36",
        abdomen_2="87.63",
        abdomen_3="86.36",
    )
    text = client.get("/measurements").text
    assert "86.8" in text
    assert "16%" in text
    settings(config, sex=Sex.FEMALE)
    assert "Needs waist and hip" in client.get("/measurements").text
    assert len(readings(config)) == 4


def test_delete_removes_session_and_readings(client, config):
    save(client, form(client), neck_1="35", neck_2="36")
    response = client.post("/measurements/2026-10-08/delete", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/measurements"
    assert readings(config) == []
    assert "No measurements yet" in client.get("/measurements").text


@pytest.mark.parametrize("path", ["/measurements", "/measurements/2026-10-08/delete"])
def test_cross_origin_mutations_refused(client, config, path):
    response = client.post(
        path,
        headers={"Origin": "https://example.com"},
        data={"date": "2026-10-08", "neck_1": "35"},
    )
    assert response.status_code == 403
    assert readings(config) == []
