from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_app import FormInputs, form_data, save, stored_entries

from tdee_calculator.app import create_app
from tdee_calculator.db import make_engine
from tdee_calculator.models import Entry, Setting
from tdee_calculator.settings import load_settings
from tdee_calculator.units import EnergyUnit, WeightUnit


def read_settings(config):
    engine = make_engine(config)
    try:
        with Session(engine) as session:
            return load_settings(session)
    finally:
        engine.dispose()


def rows(config, model):
    engine = make_engine(config)
    try:
        with engine.connect() as connection:
            return list(connection.execute(select(model)))
    finally:
        engine.dispose()


def settings_data(**changes):
    return {"weight_unit": "kg", "energy_unit": "kcal", **changes}


def switch_units(client, weight="lb", energy="kJ"):
    return client.post(
        "/settings/units",
        data={"weight_unit": weight, "energy_unit": energy},
        follow_redirects=False,
    )


def test_empty_settings_page(client):
    page = client.get("/settings")
    assert page.status_code == 200
    assert "Body" in page.text
    assert "Goal" in page.text
    assert "Advanced" in page.text
    values = FormInputs(page.text).values
    assert values["goal_weight"] == ""
    assert values["tdee_window_days"] == ""
    assert 'placeholder="28"' in page.text
    assert 'placeholder="7700"' in page.text


def test_save_settings_persists_after_restart(client, config):
    assert switch_units(client).status_code == 303
    response = client.post(
        "/settings",
        data=settings_data(
            weight_unit="lb",
            energy_unit="kJ",
            sex="female",
            activity="MODERATE",
            height_ft="5",
            height_in="10",
            birth_date="1990-02-03",
            goal_weight="180",
            rate_per_week="-1",
            tdee_window_days="35",
            energy_density="14644",
        ),
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/settings?saved=1"
    stored = read_settings(config)
    assert stored.goal_weight_kg == pytest.approx(81.6466266, abs=1e-9)
    assert stored.height_cm == pytest.approx(177.8, abs=1e-9)
    assert stored.rate_kg_per_week == pytest.approx(-0.45359237, abs=1e-9)
    with TestClient(create_app(config), base_url="http://127.0.0.1:8000") as restarted:
        page = restarted.get("/settings")
        assert FormInputs(page.text).values["goal_weight"] == "180.0"
        assert "kJ/lb" in page.text


def test_invalid_settings_preserve_text_and_all_rows(client, config):
    client.post("/settings", data=settings_data(goal_weight="75", height_cm="180"))
    before = rows(config, Setting)
    response = client.post(
        "/settings",
        data=settings_data(
            goal_weight="oops", height_cm="99", sex="male", tdee_window_days="13"
        ),
    )
    assert response.status_code == 422
    assert FormInputs(response.text).values["goal_weight"] == "oops"
    assert 'value="male" selected' in response.text
    assert "Height" in response.text
    assert "Window must be between 14 and 56" in response.text
    assert rows(config, Setting) == before


def test_invalid_units_do_not_save(client, config):
    before = rows(config, Setting)
    response = switch_units(client, weight="stone", energy="joules")
    assert response.status_code == 422
    assert "Choose kg or lb" in response.text
    assert "Choose kcal or kJ" in response.text
    assert rows(config, Setting) == before


def test_switching_units_preserves_entries_and_other_settings(client, config):
    save(client)
    client.post("/settings", data=settings_data(goal_weight="75.25", height_cm="177.8"))
    before = rows(config, Entry)
    settings = read_settings(config)
    assert switch_units(client).status_code == 303
    assert rows(config, Entry) == before
    assert read_settings(config) == replace(
        settings, weight_unit=WeightUnit.LB, energy_unit=EnergyUnit.KJ
    )
    page = client.get("/")
    values = FormInputs(page.text).values
    assert values["weight"] == "176.9"
    assert values["calories"] == "8368"
    assert "Weight (lb)" in page.text
    assert "Calories (kJ)" in page.text
    assert 'min="44.1"' in page.text
    assert 'max="881.8"' in page.text
    assert switch_units(client, "kg", "kcal").status_code == 303
    assert rows(config, Entry) == before


def test_inches_input_limit_matches_server(client):
    switch_units(client)
    page = client.get("/settings").text
    tag = page[
        page.index('id="height_in"') : page.index(">", page.index('id="height_in"'))
    ]
    # The server requires inches below 12, so the browser must not offer 12.
    assert 'max="11.5"' in tag


def test_imperial_entry_edit_preserves_weight(client, config):
    switch_units(client)
    data = FormInputs(client.get("/").text).values
    data.update(weight="180.1", calories="8368")
    assert save(client, data).status_code == 303
    assert stored_entries(config)[0][1:3] == (
        pytest.approx(81.691985837, abs=1e-9),
        2000,
    )
    data = FormInputs(client.get("/").text).values
    original = stored_entries(config)[0][1]
    data["calories"] = "8786"
    assert save(client, data).status_code == 303
    assert stored_entries(config)[0][1] == original
    assert stored_entries(config)[0][2] == 2100


@pytest.mark.parametrize("path", ["/entries", "/settings"])
@pytest.mark.parametrize("weight,energy", [("lb", "kcal"), ("kg", "kJ")])
def test_stale_units_render_fresh_and_recovery_is_safe(
    client, config, path, weight, energy
):
    save(client)
    client.post("/settings", data=settings_data(goal_weight="75", height_cm="180"))
    stale = (
        form_data(weight="80")
        if path == "/entries"
        else settings_data(goal_weight="80")
    )
    switch_units(client, weight, energy)
    before_entries, before_settings = rows(config, Entry), rows(config, Setting)
    response = client.post(path, data=stale, follow_redirects=False)
    assert response.status_code == 409
    assert "Your units changed since this page loaded" in response.text
    values = FormInputs(response.text).values
    assert values["weight_unit"] == weight
    assert values["energy_unit"] == energy
    key = "weight" if path == "/entries" else "goal_weight"
    assert values[key] != "80"
    assert rows(config, Entry) == before_entries
    assert rows(config, Setting) == before_settings
    values[key] = "165" if weight == "lb" else "75"
    assert client.post(path, data=values, follow_redirects=False).status_code == 303
    actual = (
        stored_entries(config)[0][1]
        if path == "/entries"
        else read_settings(config).goal_weight_kg
    )
    assert actual == pytest.approx(74.84274105 if weight == "lb" else 75, abs=1e-9)


@pytest.mark.parametrize("path", ["/entries", "/settings"])
def test_missing_unit_fields_refused(client, config, path):
    before = rows(config, Setting), rows(config, Entry)
    response = client.post(path, data={"weight": "80", "goal_weight": "80"})
    assert response.status_code == 409
    assert (rows(config, Setting), rows(config, Entry)) == before


@pytest.mark.parametrize("path", ["/settings", "/settings/units"])
def test_settings_cross_origin_refused(client, config, path):
    before = rows(config, Setting)
    response = client.post(
        path,
        data=settings_data(goal_weight="80"),
        headers={"Origin": "http://evil.example"},
    )
    assert response.status_code == 403
    assert rows(config, Setting) == before
