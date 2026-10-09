import csv
import io
from datetime import date, datetime

import pytest

from tdee_calculator.export import entries_csv
from tdee_calculator.models import Entry

HEADER = "date,weight_kg,calories_kcal,source,created_at,updated_at\r\n"


def entry(**overrides) -> Entry:
    return Entry(
        **{
            "date": date(2026, 10, 8),
            "weight_kg": 80.5,
            "calories": 2100,
            "source": "manual",
            "created_at": datetime(2026, 10, 8, 8),
            "updated_at": datetime(2026, 10, 8, 9, 30),
            **overrides,
        }
    )


def test_empty_export_has_only_header() -> None:
    assert entries_csv([]) == HEADER


def test_full_entry_has_expected_columns_and_line_endings() -> None:
    assert entries_csv([entry()]) == (
        HEADER + "2026-10-08,80.5,2100,manual,2026-10-08T08:00:00,"
        "2026-10-08T09:30:00\r\n"
    )


def test_timestamp_microseconds_round_trip() -> None:
    created = datetime(2026, 10, 8, 8, 0, 0, 123456)
    updated = datetime(2026, 10, 8, 9, 30, 0, 654321)
    rows = list(
        csv.reader(
            io.StringIO(entries_csv([entry(created_at=created, updated_at=updated)]))
        )
    )
    assert rows[1][4:] == [
        "2026-10-08T08:00:00.123456",
        "2026-10-08T09:30:00.654321",
    ]
    assert datetime.fromisoformat(rows[1][4]) == created
    assert datetime.fromisoformat(rows[1][5]) == updated


@pytest.mark.parametrize(
    "weight,calories,expected",
    [(None, 2100, ["", "2100"]), (80.5, None, ["80.5", ""]), (None, 0, ["", "0"])],
)
def test_missing_values_are_empty_and_zero_is_preserved(weight, calories, expected):
    rows = list(
        csv.reader(
            io.StringIO(entries_csv([entry(weight_kg=weight, calories=calories)]))
        )
    )
    assert rows[1][1:3] == expected


def test_stored_float_round_trips_exactly() -> None:
    stored = 81.6466266  # Independently established kg equivalent of 180 lb.
    rows = list(csv.reader(io.StringIO(entries_csv([entry(weight_kg=stored)]))))
    # Exact equality is intentional: serialization must preserve the stored float.
    assert float(rows[1][1]) == stored


def test_export_preserves_iterable_order() -> None:
    rows = list(
        csv.reader(
            io.StringIO(entries_csv(iter([entry(), entry(date=date(2026, 10, 7))])))
        )
    )
    assert [row[0] for row in rows[1:]] == ["2026-10-08", "2026-10-07"]
