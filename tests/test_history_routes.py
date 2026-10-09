import csv
import io
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session
from test_app import form_data, save

from tdee_calculator import clock
from tdee_calculator.db import make_engine
from tdee_calculator.models import Entry
from tdee_calculator.settings import Settings, save_settings
from tdee_calculator.units import EnergyUnit, WeightUnit

EXPECTED_COLUMNS = [
    "date",
    "weight_kg",
    "calories_kcal",
    "source",
    "created_at",
    "updated_at",
]


def test_empty_csv_download_has_header_and_download_headers(client) -> None:
    response = client.get("/entries.csv")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == (
        'attachment; filename="tdee-entries-2026-10-08.csv"'
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
    assert list(csv.reader(io.StringIO(response.text))) == [EXPECTED_COLUMNS]
    assert response.content == (
        b"date,weight_kg,calories_kcal,source,created_at,updated_at\r\n"
    )


def test_exported_rows_are_oldest_first_with_saved_values(client) -> None:
    for day, weight, calories in [
        ("2026-10-08", "80.5", "2100"),
        ("2026-10-06", "", "0"),
        ("2026-10-07", "80.25", ""),
    ]:
        assert save(client, form_data(day, weight, calories)).status_code == 303
    rows = list(csv.reader(io.StringIO(client.get("/entries.csv").text)))
    assert rows[0] == EXPECTED_COLUMNS
    assert rows[1:] == [
        [day, weight, calories, "manual", "2026-10-08T08:00:00", "2026-10-08T08:00:00"]
        for day, weight, calories in [
            ("2026-10-06", "", "0"),
            ("2026-10-07", "80.25", ""),
            ("2026-10-08", "80.5", "2100"),
        ]
    ]


def test_export_includes_rows_beyond_history_limit(client) -> None:
    for offset in range(35):
        day = (date(2026, 10, 8) - timedelta(days=offset)).isoformat()
        assert save(client, form_data(day)).status_code == 303
    rows = list(csv.reader(io.StringIO(client.get("/entries.csv").text)))
    assert len(rows) == 36
    assert [row[0] for row in rows[1:]] == [
        (date(2026, 10, 8) - timedelta(days=offset)).isoformat()
        for offset in reversed(range(35))
    ]
    assert rows[1][0] == "2026-09-04"
    assert rows[-1][0] == "2026-10-08"


def test_export_uses_stored_units_and_precision(client, config) -> None:
    engine = make_engine(config)
    try:
        with Session(engine) as session:
            save_settings(
                session, Settings(weight_unit=WeightUnit.LB, energy_unit=EnergyUnit.KJ)
            )
        values = form_data(weight="180", calories="8368")
        values.update(weight_unit="lb", energy_unit="kJ")
        assert save(client, values).status_code == 303
        rows = list(csv.reader(io.StringIO(client.get("/entries.csv").text)))
        assert rows[0] == EXPECTED_COLUMNS
        with Session(engine) as session:
            stored = session.get(Entry, date(2026, 10, 8))
            assert stored is not None
            # Exact equality verifies that export does not round stored values.
            assert float(rows[1][1]) == stored.weight_kg
        assert rows[1][1:3] == ["81.6466266", "2000"]
    finally:
        engine.dispose()


def test_export_preserves_persisted_timestamp_precision(client, monkeypatch) -> None:
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 10, 8, 8, 0, 0, 123456))
    assert save(client).status_code == 303
    values = form_data(calories="2200")
    values["loaded_version"] = "2026-10-08T08:00:00.123456"
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 10, 8, 9, 30, 0, 654321))
    assert save(client, values).status_code == 303
    rows = list(csv.reader(io.StringIO(client.get("/entries.csv").text)))
    assert rows[1][4:] == [
        "2026-10-08T08:00:00.123456",
        "2026-10-08T09:30:00.654321",
    ]


def test_export_rejects_untrusted_host(client) -> None:
    assert (
        client.get("/entries.csv", headers={"Host": "evil.example"}).status_code == 400
    )


@pytest.mark.parametrize("has_entries", [False, True])
def test_history_has_download_link_even_when_empty(client, has_entries) -> None:
    if has_entries:
        assert save(client).status_code == 303
    assert (
        '<a href="/entries.csv" download>Download CSV</a>'
        in client.get("/history").text
    )
