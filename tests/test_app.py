from datetime import date, timedelta
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tdee_calculator.app import create_app
from tdee_calculator.db import make_engine
from tdee_calculator.models import Entry


def test_history_page_shows_zero_entries(client) -> None:
    response = client.get("/history")
    assert response.status_code == 200
    assert "0 entries" in response.text
    assert "No entries yet" in response.text
    assert 'aria-current="page">History' in response.text


def test_app_startup_creates_database(config) -> None:
    assert not config.data_dir.exists()

    with TestClient(create_app(config)):
        pass

    assert config.db_path.exists()


class FormInputs(HTMLParser):
    def __init__(self, html: str, action: str | None = None) -> None:
        super().__init__()
        self.values: dict[str, str] = {}
        self.inputs: dict[str, dict[str, str | None]] = {}
        self.forms: list[dict[str, str | None]] = []
        self.action = action
        self.in_form = False
        self.feed(html)

    def handle_starttag(self, tag, attrs) -> None:
        attributes = dict(attrs)
        if tag == "form":
            self.forms.append(attributes)
            self.in_form = (
                attributes.get("action") == self.action
                if self.action is not None
                else attributes.get("method", "get").lower() == "post"
            )
        if self.in_form and tag == "input" and "name" in attributes:
            self.values[attributes["name"]] = attributes.get("value", "")
            self.inputs[attributes["name"]] = attributes

    def handle_endtag(self, tag) -> None:
        if tag == "form":
            self.in_form = False


def test_date_selector_loads_day_separately_from_save(client, config) -> None:
    save(client, form_data(entry_date="2026-10-07", calories=""))
    page = client.get("/?range=4w").text
    selector = FormInputs(page, action="/")
    assert selector.values == {"date": "2026-10-08", "range": "4w"}
    assert "onchange" not in selector.inputs["date"]
    assert selector.inputs["date"]["max"] == "2026-10-08"
    assert "required" in selector.inputs["date"]
    assert "Load day</button>" not in page
    assert 'class="logging-day"' not in page
    assert '<script src="/static/date-selector.js" defer></script>' in page
    selector.values["date"] = "2026-10-07"
    loaded = client.get("/", params=selector.values)
    entry = FormInputs(loaded.text, action="/entries")
    assert entry.inputs["entry_date"]["type"] == "hidden"
    assert entry.values["entry_date"] == "2026-10-07"
    assert entry.values["loaded_date"] == "2026-10-07"
    assert entry.values["weight"] == "80.2"
    assert FormInputs(loaded.text, action="/").values["date"] == "2026-10-07"
    assert [form["method"] for form in entry.forms] == ["get", "post"]
    entry.values["calories"] = "2100"
    response = save(client, entry.values)
    assert response.status_code == 303
    assert response.headers["location"] == (
        "/?date=2026-10-07&range=4w&saved=2026-10-07"
    )
    assert stored_entries(config) == [
        ("2026-10-07", pytest.approx(80.25, abs=1e-9), 2100, "manual")
    ]


def stored_entries(config):
    engine = make_engine(config)
    try:
        with Session(engine) as session:
            return [
                (row.date.isoformat(), row.weight_kg, row.calories, row.source)
                for row in session.scalars(select(Entry).order_by(Entry.date.desc()))
            ]
    finally:
        engine.dispose()


def form_data(entry_date="2026-10-08", weight="80.25", calories="2000"):
    return {
        "entry_date": entry_date,
        "loaded_date": entry_date,
        "loaded_version": "",
        "weight_unit": "kg",
        "energy_unit": "kcal",
        "weight": weight,
        "calories": calories,
        "range": "3m",
    }


def save(client, data=None, headers=None):
    return client.post(
        "/entries",
        data=form_data() if data is None else data,
        headers=headers,
        follow_redirects=False,
    )


def test_home_prefills_today_and_focuses_weight(client) -> None:
    response = client.get("/")
    values = FormInputs(response.text).values
    assert values == {
        "entry_date": "2026-10-08",
        "loaded_date": "2026-10-08",
        "loaded_version": "",
        "weight_unit": "kg",
        "energy_unit": "kcal",
        "weight": "",
        "calories": "",
        "range": "3m",
    }
    assert 'max="2026-10-08"' in response.text
    assert "autofocus" in response.text


def test_save_redirects_and_persists(client, config) -> None:
    response = save(client)
    assert response.status_code == 303
    assert response.headers["location"] == (
        "/?date=2026-10-08&range=3m&saved=2026-10-08"
    )
    assert stored_entries(config) == [
        ("2026-10-08", pytest.approx(80.25, abs=1e-9), 2000, "manual")
    ]
    page = client.get(response.headers["location"])
    assert "Saved Thu 8 Oct" in page.text
    assert ">Save</button>" in page.text
    assert "1 entry" in client.get("/history").text


def test_evening_calories_keep_prefilled_morning_weight(client, config) -> None:
    assert save(client, form_data(calories="")).status_code == 303
    values = FormInputs(client.get("/").text).values
    assert values["weight"] == "80.2"
    assert values["calories"] == ""
    values["calories"] = "2100"
    assert save(client, values).status_code == 303
    assert stored_entries(config) == [
        ("2026-10-08", pytest.approx(80.25, abs=1e-9), 2100, "manual")
    ]


@pytest.mark.parametrize("date_text", ["", "garbage", "2026-10-09"])
def test_invalid_selected_date_falls_back_to_today(client, date_text) -> None:
    response = client.get("/", params={"date": date_text, "range": "all"})
    assert response.status_code == 200
    entry = FormInputs(response.text)
    assert entry.values["entry_date"] == "2026-10-08"
    assert entry.values["range"] == "all"
    assert FormInputs(response.text, action="/").values["date"] == "2026-10-08"


def test_backfilled_weight_keeps_existing_calories(client, config) -> None:
    save(client, form_data(entry_date="2026-10-07", weight="", calories="0"))
    page = client.get("/?date=2026-10-07&range=4w").text
    values = FormInputs(page).values
    values["weight"] = "80.25"
    assert save(client, values).status_code == 303
    assert stored_entries(config) == [
        ("2026-10-07", pytest.approx(80.25, abs=1e-9), 0, "manual")
    ]


@pytest.mark.parametrize("failure", ["invalid", "stale", "units", "date"])
def test_save_error_keeps_selected_range(client, failure) -> None:
    values = FormInputs(client.get("/?range=4w").text).values
    if failure == "invalid":
        values["weight"] = "oops"
    elif failure == "units":
        values.update(weight="80", weight_unit="lb")
    else:
        save(client)
        values["weight"] = "81"
        if failure == "date":
            values["loaded_date"] = "2026-10-07"
    response = save(client, values)
    assert response.status_code == (422 if failure == "invalid" else 409)
    assert FormInputs(response.text).values["range"] == "4w"
    assert FormInputs(response.text, action="/").values["range"] == "4w"


def test_stale_form_cannot_overwrite_newer_save(client, config) -> None:
    stale_tab = FormInputs(client.get("/").text).values
    fresh_tab = FormInputs(client.get("/").text).values
    fresh_tab["weight"] = "80.25"
    assert save(client, fresh_tab).status_code == 303

    stale_tab["calories"] = "2100"
    response = save(client, stale_tab)

    assert response.status_code == 409
    assert "8 Oct changed since this page loaded" in response.text
    assert 'href="/?date=2026-10-08&amp;range=3m"' in response.text
    values = FormInputs(response.text).values
    assert values == stale_tab
    assert save(client, values).status_code == 409
    assert stored_entries(config) == [
        ("2026-10-08", pytest.approx(80.25, abs=1e-9), None, "manual")
    ]


def test_stale_form_cannot_recreate_deleted_entry(client, config) -> None:
    save(client)
    stale_tab = FormInputs(client.get("/").text).values
    client.post("/entries/2026-10-08/delete")

    response = save(client, stale_tab)

    assert response.status_code == 409
    assert "8 Oct changed since this page loaded" in response.text
    assert stored_entries(config) == []


def test_second_save_replaces_values_without_duplicate(client, config) -> None:
    save(client)
    values = FormInputs(client.get("/").text).values
    values.update(weight="", calories="0")
    assert save(client, values).status_code == 303
    assert stored_entries(config) == [("2026-10-08", None, 0, "manual")]
    values = FormInputs(client.get("/").text).values
    assert values["weight"] == ""
    assert values["calories"] == "0"


@pytest.mark.parametrize("existing", [False, True])
def test_invalid_save_preserves_values_and_database(client, config, existing) -> None:
    if existing:
        save(client)
    before = stored_entries(config)
    response = save(client, form_data(weight="8000", calories="2000.5"))
    assert response.status_code == 422
    assert "Weight must be between 20.0 and 400.0 kg" in response.text
    assert "Enter a whole number for calories" in response.text
    assert FormInputs(response.text).values == form_data(
        weight="8000", calories="2000.5"
    )
    assert stored_entries(config) == before


def test_empty_form_is_html_error(client, config) -> None:
    response = save(client, {"weight_unit": "kg", "energy_unit": "kcal"})
    assert response.status_code == 422
    assert "Enter a valid date" in response.text
    assert "Enter weight or calories" in response.text
    assert stored_entries(config) == []


@pytest.mark.parametrize("loaded_date", ["2026-10-07", "", "bad"])
def test_overwrite_guard_preserves_existing_entry(client, config, loaded_date) -> None:
    save(client)
    data = form_data(weight="90", calories="1900")
    data["loaded_date"] = loaded_date
    response = save(client, data)
    assert response.status_code == 409
    assert "Thu 8 Oct already has saved data" in response.text
    assert 'href="/?date=2026-10-08&amp;range=3m"' in response.text
    assert FormInputs(response.text).values == data
    assert stored_entries(config) == [
        ("2026-10-08", pytest.approx(80.25, abs=1e-9), 2000, "manual")
    ]


def test_overwrite_without_loaded_date_is_refused(client, config) -> None:
    save(client)
    data = form_data(weight="90")
    del data["loaded_date"]
    assert save(client, data).status_code == 409
    assert stored_entries(config) == [
        ("2026-10-08", pytest.approx(80.25, abs=1e-9), 2000, "manual")
    ]


@pytest.mark.parametrize("first_status", [409, 422])
def test_error_form_resubmit_cannot_bypass_guard(client, config, first_status) -> None:
    save(client)
    data = form_data(weight="8000" if first_status == 422 else "90")
    data["loaded_date"] = "2026-10-07"
    response = save(client, data)
    assert response.status_code == first_status
    values = FormInputs(response.text).values
    assert values["loaded_date"] == "2026-10-07"
    values["weight"] = "90"
    assert save(client, values).status_code == 409
    assert stored_entries(config) == [
        ("2026-10-08", pytest.approx(80.25, abs=1e-9), 2000, "manual")
    ]


@pytest.mark.parametrize("loaded_date", ["2026-10-08", "", "bad"])
def test_backfill_new_date_is_allowed(client, config, loaded_date) -> None:
    data = form_data(entry_date="2026-10-07")
    data["loaded_date"] = loaded_date
    assert save(client, data).status_code == 303
    assert stored_entries(config) == [
        ("2026-10-07", pytest.approx(80.25, abs=1e-9), 2000, "manual")
    ]


def test_guard_compares_parsed_dates(client, config) -> None:
    save(client)
    data = FormInputs(client.get("/").text).values
    data.update(loaded_date="20261008", calories="2100")
    assert save(client, data).status_code == 303
    assert stored_entries(config) == [
        ("2026-10-08", pytest.approx(80.25, abs=1e-9), 2100, "manual")
    ]


def test_edit_prefills_selected_date(client) -> None:
    save(client, form_data(entry_date="2026-10-07"))
    response = client.get("/?date=2026-10-07")
    expected = form_data(entry_date="2026-10-07")
    expected["weight"] = "80.2"
    expected["loaded_version"] = "2026-10-08T08:00:00"
    assert FormInputs(response.text).values == expected


def test_selecting_unlogged_date_shows_blank_form(client) -> None:
    save(client)
    response = client.get("/?date=2026-10-07")
    assert FormInputs(response.text).values == form_data("2026-10-07", "", "")


def test_recent_list_orders_limits_and_formats(client) -> None:
    for offset in range(32):
        entry_date = (date(2026, 10, 8) - timedelta(days=offset)).isoformat()
        assert save(client, form_data(entry_date)).status_code == 303
    page = client.get("/history").text
    assert page.index('href="/?date=2026-10-08"') < page.index(
        'href="/?date=2026-10-07"'
    )
    assert 'href="/?date=2026-09-09"' in page
    assert 'href="/?date=2026-09-08"' not in page
    assert "32 entries" in page
    assert "80.2" in page
    assert "Thu 8 Oct" in page


def test_delete_is_idempotent_and_redirects(client, config) -> None:
    save(client)
    for _ in range(2):
        response = client.post("/entries/2026-10-08/delete", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/history"
        assert stored_entries(config) == []


def test_delete_malformed_date_is_rejected(client, config) -> None:
    save(client)
    assert client.post("/entries/not-a-date/delete").status_code == 422
    assert len(stored_entries(config)) == 1


@pytest.mark.parametrize(
    "headers",
    [
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
        {"Origin": "http://evil.example"},
        {"Origin": "null"},
    ],
)
def test_cross_origin_create_and_delete_leave_database_unchanged(
    client, config, headers
) -> None:
    response = save(client, headers=headers)
    assert response.status_code == 403
    assert stored_entries(config) == []
    save(client)
    response = client.post("/entries/2026-10-08/delete", headers=headers)
    assert response.status_code == 403
    assert stored_entries(config) == [
        ("2026-10-08", pytest.approx(80.25, abs=1e-9), 2000, "manual")
    ]


@pytest.mark.parametrize(
    "headers",
    [
        {"Sec-Fetch-Site": "same-origin"},
        {"Sec-Fetch-Site": "none"},
        {"Origin": "http://127.0.0.1:8000"},
    ],
)
def test_same_origin_save_is_allowed(client, headers) -> None:
    assert save(client, headers=headers).status_code == 303


@pytest.mark.parametrize("host", ["evil.example", "localhost.evil.example"])
def test_untrusted_host_is_refused(client, config, host) -> None:
    assert client.get("/", headers={"Host": host}).status_code == 400
    assert save(client, headers={"Host": host}).status_code == 400
    assert stored_entries(config) == []


@pytest.mark.parametrize("host", ["localhost:8000", "127.0.0.1:8000", "[::1]:8000"])
def test_local_hosts_are_allowed(client, host) -> None:
    assert client.get("/", headers={"Host": host}).status_code == 200
