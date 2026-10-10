from datetime import date

import pytest

from tdee_calculator.units import WeightUnit
from tdee_calculator.web import change_phrase, requested_day, short_date


def test_short_date_adds_year_only_outside_current_year():
    today = date(2026, 10, 8)
    assert short_date(date(2026, 10, 3), today) == "Sat 3 Oct"
    assert short_date(date(2025, 12, 31), today) == "Wed 31 Dec 2025"


@pytest.mark.parametrize(
    "rate,ongoing,expected",
    [
        (-0.5, False, "lose 0.50 kg a week"),
        (0.25, False, "gain 0.25 kg a week"),
        (0, False, "maintain your weight"),
        (-0.42, True, "losing 0.42 kg a week"),
        (0.1, True, "gaining 0.10 kg a week"),
        (-0.001, True, "holding steady"),
    ],
)
def test_change_phrase(rate, ongoing, expected):
    assert change_phrase(rate, WeightUnit.KG, ongoing) == expected


def test_change_phrase_in_pounds():
    # 0.45359237 kg is exactly 1 lb.
    assert change_phrase(-0.45359237, WeightUnit.LB) == "lose 1.00 lb a week"


@pytest.mark.parametrize(
    "text,expected",
    [
        (None, date(2026, 10, 8)),
        ("", date(2026, 10, 8)),
        ("not-a-date", date(2026, 10, 8)),
        ("2026-10-09", date(2026, 10, 8)),  # the future loads today
        ("2026-10-08", date(2026, 10, 8)),
        ("2025-02-01", date(2025, 2, 1)),
    ],
)
def test_requested_day(text, expected):
    assert requested_day(text, date(2026, 10, 8)) == expected
