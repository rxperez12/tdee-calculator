from dataclasses import dataclass
from datetime import date, datetime

import pytest

from tdee_calculator.edits import edit_conflict, row_version

DAY = date(2026, 10, 8)
LOADED_AT = datetime(2026, 10, 8, 8, 0, 0, 123456)


@dataclass(frozen=True)
class Row:
    updated_at: datetime


def test_row_version_is_the_exact_timestamp_or_empty():
    assert row_version(Row(LOADED_AT)) == "2026-10-08T08:00:00.123456"
    assert row_version(None) == ""


@pytest.mark.parametrize(
    "loaded_date,loaded_version,current,expected",
    [
        # Same date the form loaded.
        ("2026-10-08", "2026-10-08T08:00:00.123456", Row(LOADED_AT), None),
        ("2026-10-08", "", None, None),  # new day, still empty
        (
            "2026-10-08",
            "2026-10-08T08:00:00.123456",
            Row(datetime(2026, 10, 8, 9)),
            "stale",
        ),
        ("2026-10-08", "2026-10-08T08:00:00.123456", None, "stale"),  # deleted since
        ("2026-10-08", "", Row(LOADED_AT), "stale"),  # created in another tab
        # A different date, or no usable loaded date.
        ("2026-10-07", "2026-10-07T08:00:00", Row(LOADED_AT), "conflict"),
        ("2026-10-07", "2026-10-07T08:00:00", None, None),
        ("", "", Row(LOADED_AT), "conflict"),
        ("not-a-date", "", Row(LOADED_AT), "conflict"),
        ("", "", None, None),
    ],
)
def test_edit_conflict(loaded_date, loaded_version, current, expected):
    assert edit_conflict(DAY, loaded_date, loaded_version, current) == expected
