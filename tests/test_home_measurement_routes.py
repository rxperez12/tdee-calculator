import re
from datetime import date, datetime
from html import escape, unescape

import pytest
from test_app import FormInputs, stored_entries
from test_dashboard import linear_logs
from test_dashboard_routes import chart_data, section, seed
from test_measurement_routes import readings, save, settings

from tdee_calculator import clock
from tdee_calculator.calc import Sex
from tdee_calculator.settings import Settings
from tdee_calculator.units import WeightUnit

pytestmark = pytest.mark.usefixtures("measurement_profile")


def home_form(client, *, day="2026-10-08", daily_day="2026-10-02", chart_range="4w"):
    return FormInputs(
        client.get(
            "/",
            params={"date": daily_day, "range": chart_range, "circumference_date": day},
        ).text,
        action="/measurements",
    ).values


def measurement_section(html):
    return html.split('<section class="home-measurements"')[1].split("</section>")[0]


def assert_home_feedback(response, *, daily_day="2026-10-02", chart_range="4w"):
    assert "<h1>Today</h1>" in response.text
    assert '<details class="circumference-log" open>' in response.text
    daily = FormInputs(response.text, action="/entries").values
    assert daily["entry_date"] == daily_day
    assert daily["range"] == chart_range
    assert "autofocus" not in response.text


@pytest.mark.parametrize(
    "weight,text", [(WeightUnit.KG, "39.37"), (WeightUnit.LB, "15.5")]
)
def test_home_save_keeps_daily_context_and_stores_cm(client, config, weight, text):
    settings(config, weight=weight)
    values = home_form(client)
    assert values["source"] == "home"
    assert values["home_date"] == "2026-10-02"
    response = save(client, values, neck_1=text)
    assert response.status_code == 303
    assert response.headers["location"] == (
        "/?date=2026-10-02&range=4w&circumference_date=2026-10-08&circumference_saved=2026-10-08"
    )
    page = client.get(response.headers["location"])
    assert_home_feedback(page)
    assert "Saved measurements for Thu 8 Oct" in measurement_section(page.text)
    assert "Saved Thu 8 Oct" not in page.text
    assert readings(config) == [("neck", 1, pytest.approx(39.37, abs=1e-9))]
    assert stored_entries(config) == []


@pytest.mark.parametrize(
    "changes",
    [{}, {"neck_1": "nan"}, {"date": ""}, {"date": "bad"}, {"date": "2026-10-09"}],
)
def test_home_validation_keeps_values_without_saving(client, config, changes):
    values = home_form(client)
    response = save(client, values, **changes)
    assert response.status_code == 422
    assert_home_feedback(response)
    returned = FormInputs(response.text, action="/measurements").values
    for key, value in changes.items():
        assert returned[key] == value
    assert readings(config) == []
    assert stored_entries(config) == []


def test_home_overwrite_guard_links_to_home_and_keeps_both_dates(client, config):
    assert (
        save(client, home_form(client, day="2026-10-07"), neck_1="35").status_code
        == 303
    )
    assert save(client, home_form(client), neck_1="37").status_code == 303
    response = save(client, home_form(client), date="2026-10-07", neck_1="40")
    assert response.status_code == 409
    assert_home_feedback(response)
    assert (
        'href="/?date=2026-10-02&amp;range=4w&amp;circumference_date=2026-10-07"'
        in response.text
    )
    assert "Edit this session" in response.text
    assert readings(config) == [("neck", 1, 35), ("neck", 1, 37)]


def test_home_stale_and_deleted_sessions_are_not_overwritten(
    client, config, monkeypatch
):
    save(client, home_form(client), neck_1="35")
    stale = home_form(client)
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 10, 8, 9))
    save(client, home_form(client), neck_1="36")
    response = save(client, stale, neck_1="37")
    assert response.status_code == 409
    assert_home_feedback(response)
    assert "Reload this session" in response.text
    assert (
        'href="/?date=2026-10-02&amp;range=4w&amp;circumference_date=2026-10-08"'
        in response.text
    )
    assert readings(config) == [("neck", 1, 36)]
    client.post("/measurements/2026-10-08/delete")
    assert save(client, stale, neck_1="38").status_code == 409
    assert readings(config) == []


def test_home_concurrent_creation_refuses_stale_empty_form(client, config):
    stale = home_form(client)
    save(client, home_form(client), neck_1="35")
    response = save(client, stale, neck_1="40")
    assert response.status_code == 409
    assert_home_feedback(response)
    assert readings(config) == [("neck", 1, 35)]


def test_home_stale_units_reload_current_readings(client, config):
    save(client, home_form(client), neck_1="39.37")
    stale = home_form(client)
    settings(config, weight=WeightUnit.LB)
    response = save(client, stale, neck_1="73.123456")
    assert response.status_code == 409
    assert_home_feedback(response)
    assert "Your units changed" in measurement_section(response.text)
    returned = FormInputs(response.text, action="/measurements").values
    assert returned["neck_1"] == "15.5"
    assert returned["weight_unit"] == "lb"
    assert "73.123456" not in response.text
    assert readings(config) == [("neck", 1, 39.37)]


def test_home_energy_unit_change_and_unchanged_edits_preserve_cm(client, config):
    save(client, home_form(client), neck_1="39.3712345")
    original = readings(config)
    stale = home_form(client)
    client.post("/settings/units", data={"weight_unit": "kg", "energy_unit": "kJ"})
    assert save(client, stale).status_code == 303
    for unit in (WeightUnit.LB, WeightUnit.KG):
        settings(config, weight=unit)
        assert save(client, home_form(client)).status_code == 303
        assert readings(config) == original


@pytest.mark.parametrize("source", [None, "unknown", "https://example.com"])
def test_unknown_sources_keep_standalone_save_behavior(client, config, source):
    values = home_form(client)
    values.pop("source")
    if source is not None:
        values["source"] = source
    response = save(client, values, neck_1="35")
    assert response.status_code == 303
    assert (
        response.headers["location"] == "/measurements?date=2026-10-08&saved=2026-10-08"
    )
    assert readings(config) == [("neck", 1, 35)]


def test_home_context_is_normalized_and_cross_origin_save_refused(client, config):
    values = home_form(client)
    refused = client.post(
        "/measurements",
        data={**values, "neck_1": "35"},
        headers={"Origin": "https://example.com"},
    )
    assert refused.status_code == 403
    assert readings(config) == []
    response = save(
        client, values, neck_1="35", home_date="https://example.com", range="bad"
    )
    assert response.headers["location"] == (
        "/?date=2026-10-08&range=3m&circumference_date=2026-10-08&circumference_saved=2026-10-08"
    )


def test_home_empty_default_and_explicit_date_loading(client):
    page = client.get("/").text
    assert "No measurements yet. Log your first session." in page
    assert '<details class="circumference-log" >' in page
    assert "autofocus" in page
    assert FormInputs(page, action="/measurements").values["date"] == "2026-10-08"
    for day in ("", "bad", "2026-10-09"):
        response = client.get("/", params={"circumference_date": day})
        assert_home_feedback(response, daily_day="2026-10-08", chart_range="3m")
        assert (
            FormInputs(response.text, action="/measurements").values["date"]
            == "2026-10-08"
        )


def test_partial_summary_and_latest_edit_keep_distinct_dates(client, config):
    settings(config)
    save(client, home_form(client, day="2026-10-03"), neck_1="39.37", abdomen_1="88.9")
    save(client, home_form(client), neck_1="35")
    response = client.get("/?date=2026-10-02&range=all")
    section = measurement_section(response.text)
    assert "18%" in section
    assert "Needs abdomen" in section
    assert 'datetime="2026-10-03"' in section
    assert 'datetime="2026-10-08"' in section
    assert 'datetime="2026-10-15"' in section
    assert "35.0 cm" in section
    assert "39.4 cm" not in section
    assert (
        'href="/?date=2026-10-02&amp;range=all&amp;circumference_date=2026-10-08"'
        in section
    )
    assert 'id="chart"' not in response.text
    loaded = home_form(client)
    assert loaded["neck_1"] == "35.0"
    assert loaded["abdomen_1"] == ""
    assert loaded["loaded_version"]
    assert re.search(
        r'<dd class="circumference-estimate-value">\s*18%\s*</dd>', section
    )
    assert '<details class="measurement-about">' in section
    explanation = section.split('<details class="measurement-about">')[1].split(
        "</details>"
    )[0]
    assert "uncertainty of several percentage points" in explanation
    assert "does not change your calorie target" in explanation


@pytest.mark.parametrize("status", [422, 409])
def test_daily_failures_keep_measurements_collapsed_and_ids_unique(client, status):
    save(client, home_form(client), neck_1="35")
    values = FormInputs(client.get("/").text, action="/entries").values
    if status == 409:
        assert (
            client.post("/entries", data={**values, "weight": "80"}).status_code == 200
        )
        values["weight"] = "81"
    else:
        values["weight"] = "bad"
    response = client.post("/entries", data=values)
    assert response.status_code == status
    assert '<details class="circumference-log" >' in response.text
    assert "35.0 cm" in measurement_section(response.text)
    ids = re.findall(r'\bid="([^"]+)"', response.text)
    assert len(ids) == len(set(ids))
    forms = re.findall(r"<form\b.*?</form>", response.text, re.DOTALL)
    assert len(forms) == 3
    assert all(form.count("<form") == 1 for form in forms)
    assert "autofocus" in response.text


def test_measurement_date_error_is_associated_with_its_control(client):
    response = save(client, home_form(client), date="bad", neck_1="35")
    inputs = FormInputs(response.text, action="/measurements")
    assert inputs.inputs["date"]["aria-describedby"] == "measurement-date-error"
    assert 'id="measurement-date-error"' in response.text
    assert "Enter a valid date." in unescape(response.text)


@pytest.mark.parametrize(
    "today,copy",
    [
        (date(2026, 10, 9), "next suggested Sat 10 Oct."),
        (date(2026, 10, 10), "suggested measurement today."),
        (date(2026, 10, 12), "next suggested Sat 10 Oct. Log when ready."),
    ],
)
def test_home_cadence_copy(client, monkeypatch, today, copy):
    save(client, home_form(client, day="2026-10-03"), neck_1="35")
    monkeypatch.setattr(clock, "today", lambda: today)
    text = re.sub(r"<[^>]+>", "", measurement_section(client.get("/").text))
    assert copy in " ".join(text.split())


@pytest.mark.parametrize(
    "sex,height,changes,expected",
    [
        (None, None, {"neck_1": "35"}, "Set sex and height in Settings"),
        (Sex.MALE, 180, {"neck_1": "35"}, "Needs abdomen"),
        (
            Sex.MALE,
            180,
            {"neck_1": "40", "abdomen_1": "40"},
            "Outside the equation's range",
        ),
    ],
)
def test_home_all_unusable_estimates_keep_readings(
    client, config, sex, height, changes, expected
):
    settings(config, sex=sex or Sex.MALE, height=height)
    save(client, home_form(client), **changes)
    settings(config, sex=sex, height=height)
    summary = measurement_section(client.get("/").text)
    assert expected in unescape(summary)
    if sex is not None:
        assert " cm" in summary
    assert 'datetime="2026-10-08"' in summary
    assert 'class="circumference-estimate-value"' not in summary
    if sex is None:
        assert '<a href="/settings">' in summary


def test_backfills_corrections_extra_sessions_and_delete_update_cadence(
    client, config, monkeypatch
):
    save(client, home_form(client, day="2026-10-03"), neck_1="35")
    save(client, home_form(client, day="2026-10-04"), abdomen_1="80")
    assert 'datetime="2026-10-11"' in measurement_section(client.get("/").text)
    save(client, home_form(client, day="2026-10-01"), neck_1="36")
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 10, 8, 9))
    save(client, home_form(client, day="2026-10-04"), abdomen_1="81")
    summary = measurement_section(client.get("/").text)
    assert 'datetime="2026-10-11"' in summary
    assert "81.0 cm" in summary
    client.post("/measurements/2026-10-04/delete")
    summary = measurement_section(client.get("/").text)
    assert 'datetime="2026-10-10"' in summary
    assert "35.0 cm" in summary
    assert len(readings(config)) == 2


def test_measurements_do_not_change_daily_records_or_dashboard_results(client, config):
    seed(
        config,
        linear_logs(),
        Settings(sex=Sex.MALE, height_cm=180.34, rate_kg_per_week=-0.5),
    )
    before = client.get("/?date=2026-10-02&range=4w").text
    original = stored_entries(config)
    save(client, home_form(client), neck_1="39.37", abdomen_1="88.9")
    save(client, home_form(client), neck_1="40", abdomen_1="90")
    after = client.get("/?date=2026-10-02&range=4w").text
    assert stored_entries(config) == original
    for heading in ("tdee-heading", "hero-heading", "trend-heading"):
        assert section(after, heading) == section(before, heading)
    assert chart_data(after) == chart_data(before)
    assert "2,550 kcal" in section(after, "tdee-heading")
    assert "2,000 kcal today" in section(after, "hero-heading")


def test_daily_navigation_resets_measurement_form_only(client, config):
    seed(config, linear_logs())
    save(client, home_form(client, day="2026-10-07"), neck_1="35")
    page = client.get(
        "/?date=2026-10-02&range=4w&circumference_date=2026-10-07&circumference_saved=2026-10-07"
    ).text
    assert 'href="/?range=all&amp;date=2026-10-02#chart"' in page
    next_page = client.get("/?range=all&date=2026-10-02#chart").text
    assert '<details class="circumference-log" >' in next_page
    assert FormInputs(next_page, action="/entries").values["entry_date"] == "2026-10-02"
    assert FormInputs(next_page, action="/measurements").values["date"] == "2026-10-08"
    selector = FormInputs(page, action="/").values
    assert selector == {"date": "2026-10-02", "range": "4w"}
    next_page = client.get("/", params={**selector, "date": "2026-10-01"}).text
    assert '<details class="circumference-log" >' in next_page
    assert FormInputs(next_page, action="/entries").values["entry_date"] == "2026-10-01"
    assert FormInputs(next_page, action="/measurements").values["date"] == "2026-10-08"


def test_home_log_link_loads_today_and_blank_new_dates(client):
    save(client, home_form(client), neck_1="35")
    page = client.get("/?date=2026-10-02&range=all").text
    url = "/?date=2026-10-02&range=all&circumference_date=2026-10-08"
    assert f'href="{escape(url)}" aria-label="Log measurements">Log</a>' in page
    assert (
        FormInputs(client.get(url).text, action="/measurements").values["neck_1"]
        == "35.0"
    )
    blank = home_form(client, day="2026-10-07")
    assert blank["neck_1"] == ""
    assert blank["loaded_version"] == ""


def test_home_invalid_save_preserves_stored_session_and_typed_readings(client, config):
    save(client, home_form(client), neck_1="35")
    response = save(client, home_form(client), neck_1="bad", abdomen_2="90.12345")
    assert response.status_code == 422
    assert_home_feedback(response)
    fields = FormInputs(response.text, action="/measurements")
    assert fields.values["neck_1"] == "bad"
    assert fields.values["abdomen_2"] == "90.12345"
    assert fields.inputs["neck_1"]["aria-describedby"] == "neck_1-error"
    assert 'id="neck_1-error"' in response.text
    assert readings(config) == [("neck", 1, 35)]
