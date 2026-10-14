from datetime import date

import pytest
from sqlalchemy.orm import Session
from test_app import FormInputs
from test_measurement_routes import readings, save, settings

from tdee_calculator import measurements
from tdee_calculator.calc import Sex, Site
from tdee_calculator.db import make_engine
from tdee_calculator.measurement_form import MeasurementInput
from tdee_calculator.units import WeightUnit

DAY = date(2026, 10, 8)
ALL_READINGS = {
    Site.NECK: (39.3712345,),
    Site.ABDOMEN: (88.9012345, 89.0123456),
    Site.WAIST: (71.1212345, 72.0123456),
    Site.HIP: (96.5212345, 97.0123456, 98.0123456),
}


def page_url(page, day="2026-10-08"):
    return (
        f"/?date=2026-10-02&range=4w&circumference_date={day}"
        if page == "home"
        else f"/measurements?date={day}"
    )


def form(client, page, day="2026-10-08"):
    return FormInputs(client.get(page_url(page, day)).text, action="/measurements")


def seed_readings(config):
    engine = make_engine(config)
    try:
        with Session(engine) as session:
            measurements.upsert_session(session, MeasurementInput(DAY, ALL_READINGS))
    finally:
        engine.dispose()


@pytest.mark.parametrize("page", ["home", "measurements"])
@pytest.mark.parametrize("weight", list(WeightUnit))
@pytest.mark.parametrize(
    "sex,expected",
    [
        (Sex.MALE, {"neck", "abdomen"}),
        (Sex.FEMALE, {"neck", "waist", "hip"}),
    ],
)
def test_forms_show_only_equation_sites(client, config, page, weight, sex, expected):
    settings(config, sex=sex, weight=weight)
    inputs = form(client, page)
    assert inputs.values["sex"] == sex.value
    for site in Site:
        for slot in range(1, 4):
            assert (f"{site.value}_{slot}" in inputs.values) == (site.value in expected)
    assert "You can save a partial session" in client.get(page_url(page)).text


@pytest.mark.parametrize("page", ["home", "measurements"])
def test_unset_sex_prompts_settings_without_showing_measurement_fields(
    client, config, page
):
    settings(config, sex=None)
    inputs = form(client, page)
    assert not any(f"{site.value}_1" in inputs.values for site in Site)
    text = client.get(page_url(page)).text
    assert "Choose male or female in Settings" in text
    assert '<a href="/settings">' in text
    response = save(client, inputs.values, neck_1="35")
    assert response.status_code == 422
    assert readings(config) == []


@pytest.mark.parametrize("page", ["home", "measurements"])
@pytest.mark.parametrize(
    "sex,fields,estimate",
    [
        (Sex.MALE, {"neck_1": "39.37", "abdomen_1": "88.9"}, "18%"),
        (Sex.FEMALE, {"neck_1": "33.02", "waist_1": "71.12", "hip_1": "96.52"}, "26%"),
    ],
)
def test_selected_sites_save_and_estimate_with_partial_sessions_allowed(
    client, config, page, sex, fields, estimate
):
    settings(config, sex=sex, height=180.34 if sex == Sex.MALE else 165.1)
    response = save(client, form(client, page).values, **fields)
    assert response.status_code == 303
    assert estimate in client.get(response.headers["location"]).text
    partial = form(client, page, "2026-10-07").values
    assert save(client, partial, neck_1="35").status_code == 303


@pytest.mark.parametrize("page", ["home", "measurements"])
@pytest.mark.parametrize("weight", list(WeightUnit))
@pytest.mark.parametrize("sex", list(Sex))
def test_edit_preserves_hidden_raw_readings_and_clears_visible_sites(
    client, config, page, weight, sex
):
    settings(config, sex=sex, weight=weight)
    seed_readings(config)
    original = readings(config)
    active_other = Site.ABDOMEN if sex == Sex.MALE else Site.WAIST
    inputs = form(client, page).values
    for slot in range(1, 4):
        inputs[f"{active_other.value}_{slot}"] = ""
    # Change neck; the hidden readings must stay at their original cm precision.
    inputs["neck_1"] = "16" if weight == WeightUnit.LB else "40.64"
    assert save(client, inputs).status_code == 303
    expected = [
        (site, slot, value)
        for site, slot, value in original
        if site != active_other.value
    ]
    expected = [
        (site, slot, 40.64 if site == "neck" else value)
        for site, slot, value in expected
    ]
    actual = readings(config)
    for stored, wanted in zip(actual, expected, strict=True):
        assert stored[:2] == wanted[:2]
        assert stored[2] == pytest.approx(wanted[2], abs=1e-9)
    hidden = {"waist", "hip"} if sex == Sex.MALE else {"abdomen"}
    assert [r for r in actual if r[0] in hidden] == [
        r for r in original if r[0] in hidden
    ]


@pytest.mark.parametrize("page", ["home", "measurements"])
@pytest.mark.parametrize("sex", list(Sex))
def test_post_cannot_modify_hidden_sites(client, config, page, sex):
    settings(config, sex=sex)
    seed_readings(config)
    original = readings(config)
    hidden = "waist" if sex == Sex.MALE else "abdomen"
    response = save(
        client, form(client, page).values, **{f"{hidden}_1": "nan", f"{hidden}_3": "99"}
    )
    assert response.status_code == 303
    assert readings(config) == original
    # Moving to a new date must not copy hidden readings from the loaded session.
    response = save(client, form(client, page).values, date="2026-10-07")
    assert response.status_code == 303
    engine = make_engine(config)
    try:
        with Session(engine) as session:
            created = measurements.get_session(session, date(2026, 10, 7))
            assert created is not None
            hidden_sites = {"waist", "hip"} if sex == Sex.MALE else {"abdomen"}
            assert not any(r.site in hidden_sites for r in created.readings)
    finally:
        engine.dispose()


@pytest.mark.parametrize("page", ["home", "measurements"])
@pytest.mark.parametrize(
    "selected,changed", [(Sex.MALE, Sex.FEMALE), (Sex.FEMALE, Sex.MALE)]
)
def test_stale_sex_refreshes_form_without_writing(
    client, config, page, selected, changed
):
    settings(config, sex=selected)
    seed_readings(config)
    original = readings(config)
    stale = form(client, page).values
    settings(config, sex=changed)
    response = save(client, stale, neck_1="40")
    assert response.status_code == 409
    assert "Your sex setting changed" in response.text
    fresh = FormInputs(response.text, action="/measurements").values
    assert fresh["sex"] == changed.value
    assert ("abdomen_1" in fresh) == (changed == Sex.MALE)
    assert ("waist_1" in fresh) == (changed == Sex.FEMALE)
    assert readings(config) == original
    assert save(client, fresh).status_code == 303
    assert readings(config) == original


@pytest.mark.parametrize("page", ["home", "measurements"])
@pytest.mark.parametrize("sex", list(Sex))
def test_hidden_readings_do_not_make_an_empty_visible_form_savable(
    client, config, page, sex
):
    settings(config, sex=sex)
    seed_readings(config)
    original = readings(config)
    fields = form(client, page).values
    for key in fields:
        if key.rsplit("_", 1)[0] in {"neck", "abdomen", "waist", "hip"}:
            fields[key] = ""
    response = save(client, fields)
    assert response.status_code == 422
    assert "Enter at least one reading" in response.text
    assert readings(config) == original


@pytest.mark.parametrize("page", ["home", "measurements"])
def test_unsetting_sex_keeps_stored_readings_and_prompts_settings(client, config, page):
    settings(config)
    seed_readings(config)
    original = readings(config)
    stale = form(client, page).values
    settings(config, sex=None)
    response = save(client, stale, neck_1="40")
    assert response.status_code == 422
    assert "Choose male or female in Settings" in response.text
    assert not any(
        f"{site.value}_1" in FormInputs(response.text, action="/measurements").values
        for site in Site
    )
    assert readings(config) == original


@pytest.mark.parametrize(
    "sex,visible,hidden",
    [
        (Sex.MALE, ("Neck", "Abdomen (navel)"), ("Waist (narrowest point)", "Hips")),
        (Sex.FEMALE, ("Neck", "Waist (narrowest point)", "Hips"), ("Abdomen (navel)",)),
    ],
)
def test_home_summary_and_history_follow_selection_without_deleting_readings(
    client, config, sex, visible, hidden
):
    settings(config, sex=sex)
    seed_readings(config)
    html = client.get("/").text
    summary = html.split('<dl class="circumference-values">')[1].split("</dl>")[0]
    for label in visible:
        assert f"<dt>{label}</dt>" in summary
    for label in hidden:
        assert f"<dt>{label}</dt>" not in summary
    history = client.get("/measurements").text.split('class="measurement-history"')[1]
    for label in visible:
        assert label in history
    for label in hidden:
        assert label not in history
    assert len(readings(config)) == 8


def test_history_changes_columns_with_settings_and_preserves_rows(client, config):
    settings(config)
    seed_readings(config)
    original = readings(config)
    for sex, expected, absent in [
        (Sex.MALE, ("39.4", "89.0"), ("71.6", "97.2")),
        (Sex.FEMALE, ("39.4", "71.6", "97.2"), ("89.0",)),
        (Sex.MALE, ("39.4", "89.0"), ("71.6", "97.2")),
    ]:
        settings(config, sex=sex)
        table = client.get("/measurements").text.split('class="measurement-history"')[1]
        for value in expected:
            assert f">{value}</td>" in table
        for value in absent:
            assert f">{value}</td>" not in table
        assert readings(config) == original


def test_unset_sex_keeps_history_dates_without_guessing_columns(client, config):
    settings(config)
    seed_readings(config)
    original = readings(config)
    settings(config, sex=None)
    table = client.get("/measurements").text.split('class="measurement-history"')[1]
    assert "Thu 8 Oct" in table
    assert "Set sex in Settings" in table
    for label in ("Neck", "Abdomen (navel)", "Waist (narrowest point)", "Hips"):
        assert label not in table
    assert readings(config) == original
