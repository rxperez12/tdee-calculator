import re
from datetime import date, timedelta
from html import unescape
from urllib.parse import parse_qs, urlsplit

import pytest
from test_app import FormInputs


def link(html: str, label: str) -> str:
    match = re.search(r'href="([^"]+)"[^>]*>' + re.escape(label) + r"</a>", html)
    assert match is not None
    return unescape(match[1])


def test_home_has_calendar_and_one_ready_daily_editor(client):
    page = client.get("/").text
    assert 'id="logging-calendar"' in page
    assert page.count('action="/entries"') == 1
    assert page.count('action="/measurements"') == 1
    assert FormInputs(page, action="/entries").values["entry_date"] == "2026-10-08"
    assert "Weight streak" in page
    assert "Calorie streak" in page
    assert "autofocus" not in page


def test_calendar_save_and_recovery_keep_actual_workspace_context(client):
    page = client.get(
        "/?date=2026-09-12&month=2026-09&selection=1&stat=weight&stat=calories&range=4w"
    ).text
    form = FormInputs(page, action="/entries").values
    # The helper represents single-value forms; send both selected stats explicitly.
    response = client.post(
        "/entries",
        data={**form, "stat": ["weight", "calories"], "weight": "80", "calories": "0"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert "month=2026-09" in location
    assert "stat=weight" in location
    assert "stat=calories" in location
    saved = client.get(location).text
    assert "September 2026" in saved
    assert FormInputs(saved, action="/entries").values["weight"] == "80.0"
    assert "Both logged" in saved
    invalid = client.post(
        "/entries",
        data={**FormInputs(saved, action="/entries").values, "weight": "bad"},
    )
    assert invalid.status_code == 422
    assert "September 2026" in invalid.text
    assert FormInputs(invalid.text, action="/entries").values["weight"] == "bad"


def test_month_browsing_and_today_have_distinct_selection_effects(client):
    page = client.get("/?date=2026-09-12&month=2026-09&selection=1&range=4w").text
    following = client.get(link(page, "Next month")).text
    assert "October 2026" in following
    assert FormInputs(following, action="/entries").values["entry_date"] == "2026-09-12"
    calendar_today = link(following.split('<div class="calendar-month">')[1], "Today")
    current = client.get(calendar_today).text
    assert FormInputs(current, action="/entries").values["entry_date"] == "2026-10-08"
    assert "stat" not in FormInputs(current, action="/entries").inputs
    assert "No values selected." in current


def test_measurement_save_keeps_month_stats_and_shared_selected_day(
    client, measurement_profile
):
    page = client.get(
        "/?date=2026-09-12&month=2026-09&selection=1&stat=neck&measurements=open"
    ).text
    form = FormInputs(page, action="/measurements").values
    assert form["date"] == "2026-09-12"
    response = client.post(
        "/measurements", data={**form, "neck_1": "35"}, follow_redirects=False
    )
    assert response.status_code == 303
    saved = client.get(response.headers["location"]).text
    assert "month=2026-09" in response.headers["location"]
    assert "stat=neck" in response.headers["location"]
    assert FormInputs(saved, action="/entries").values["entry_date"] == "2026-09-12"
    assert "35.0 cm" in saved
    assert "Saved measurements" in saved


def test_more_than_recent_limit_streak_and_old_month(client):
    for offset in range(35):
        day = date(2026, 10, 8) - timedelta(days=offset)
        form = FormInputs(client.get(f"/?date={day}").text, action="/entries").values
        assert (
            client.post(
                "/entries", data={**form, "weight": "80", "calories": "0"}
            ).status_code
            == 200
        )
    page = client.get("/?month=2026-09").text
    assert 'data-streak="weight">35<' in page
    assert 'data-streak="calories">35<' in page
    assert "80.0" in page


def test_legacy_measurement_link_selects_its_day(client):
    page = client.get("/?date=2026-10-02&circumference_date=2026-10-07").text
    assert FormInputs(page, action="/entries").values["entry_date"] == "2026-10-07"
    assert FormInputs(page, action="/measurements").values["date"] == "2026-10-07"


@pytest.mark.parametrize(
    "month", ["", "bad", "2026-13", "2026-00", "202610", "https://example.com"]
)
def test_invalid_month_uses_selected_days_month(client, month):
    page = client.get("/", params={"date": "2026-09-12", "month": month}).text
    assert "September 2026" in page
    assert FormInputs(page, action="/entries").values["month"] == "2026-09"


def test_stat_allowlist_deduplicates_and_follows_profile(client, measurement_profile):
    page = client.get(
        "/?selection=1&stat=neck&stat=neck&stat=waist&stat=unknown&stat=navy"
    ).text
    day_link = link(page.split('<div class="calendar-month">')[1], "Today")
    assert parse_qs(urlsplit(day_link).query)["stat"] == ["neck", "navy"]
    assert 'name="stat" value="waist"' not in page
    assert 'name="stat" value="unknown"' not in page


@pytest.mark.parametrize("month", ["0001-01", "9999-12", "2028-02"])
def test_boundary_and_future_months_render_without_future_edit_links(client, month):
    page = client.get("/", params={"month": month}).text
    assert FormInputs(page, action="/entries").values["month"] == month
    if month == "0001-01":
        assert ">Previous month</a>" not in page
    else:
        assert 'class="calendar-date" href=' not in page
    if month == "9999-12":
        assert ">Next month</a>" not in page


def test_stale_daily_save_and_generated_reload_preserve_offscreen_context(client):
    page = client.get(
        "/?date=2026-09-12&month=2026-08&selection=1&stat=weight&stat=navy&range=4w"
    ).text
    values = FormInputs(page, action="/entries").values
    assert client.post("/entries", data={**values, "weight": "80"}).status_code == 200
    stale = client.post("/entries", data={**values, "calories": "2100"})
    assert stale.status_code == 409
    assert "August 2026" in stale.text
    assert FormInputs(stale.text, action="/entries").values["calories"] == "2100"
    recovered = client.get(link(stale.text, "reload it")).text
    assert "August 2026" in recovered
    assert FormInputs(recovered, action="/entries").values["weight"] == "80.0"
    assert FormInputs(recovered, action="/entries").values["calories"] == ""


def test_daily_selection_leaves_current_dashboard_and_chart_unchanged(client, config):
    from test_dashboard import linear_logs
    from test_dashboard_routes import chart_data, section, seed

    seed(config, linear_logs())
    current = client.get("/?range=4w").text
    editing = client.get("/?date=2026-09-12&month=2026-08&range=4w").text
    for heading in ("hero-heading", "tdee-heading", "trend-heading"):
        assert section(current, heading) == section(editing, heading)
    assert chart_data(current) == chart_data(editing)


def test_home_reads_today_once_for_calendar_and_dashboard(client, monkeypatch):
    from tdee_calculator import clock

    calls = []

    def today():
        calls.append(True)
        return date(2026, 10, 8)

    monkeypatch.setattr(clock, "today", today)
    assert client.get("/").status_code == 200
    assert calls == [True]


def test_measurement_error_keeps_disclosure_in_navigation_context(
    client, measurement_profile
):
    page = client.get("/?date=2026-09-12&month=2026-08&selection=1&stat=neck").text
    form = FormInputs(page, action="/measurements").values
    response = client.post("/measurements", data={**form, "neck_1": "nan"})
    assert response.status_code == 422
    following = link(response.text, "Next month")
    assert parse_qs(urlsplit(following).query)["measurements"] == ["open"]
    assert (
        FormInputs(response.text, action="/measurements").values["measurements"]
        == "open"
    )
