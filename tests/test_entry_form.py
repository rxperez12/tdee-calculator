from datetime import date

import pytest

from tdee_calculator.entry_form import EntryFormErrors, EntryInput, parse_entry_form

TODAY = date(2026, 10, 8)


@pytest.mark.parametrize(
    "weight,calories,expected_weight,expected_calories",
    [
        ("80.25", "2000", 80.25, 2000),
        ("80", "", 80.0, None),
        ("", "0", None, 0),
        (" 80.25 ", " 2000 ", 80.25, 2000),
        (" \t", "2000", None, 2000),
        ("80", " \t", 80.0, None),
        ("20", "0", 20.0, 0),
        ("400", "20000", 400.0, 20000),
    ],
)
def test_valid_form(weight, calories, expected_weight, expected_calories) -> None:
    result = parse_entry_form(" 2026-10-08 ", weight, calories, TODAY)
    assert isinstance(result, EntryInput)
    assert result.date == TODAY
    if expected_weight is None:
        assert result.weight_kg is None
    else:
        assert result.weight_kg == pytest.approx(expected_weight, abs=1e-9)
    assert result.calories == expected_calories


@pytest.mark.parametrize(
    "entry_date,weight,calories,field",
    [
        ("2026-10-08", "", "", "form"),
        ("2026-10-08", " \t", " \t", "form"),
        ("", "80", "2000", "date"),
        ("2026-13-01", "80", "2000", "date"),
        ("2026-10-09", "80", "2000", "date"),
        ("2026-10-08", "abc", "2000", "weight_kg"),
        ("2026-10-08", "nan", "2000", "weight_kg"),
        ("2026-10-08", "inf", "2000", "weight_kg"),
        ("2026-10-08", "-inf", "2000", "weight_kg"),
        ("2026-10-08", "19.9", "2000", "weight_kg"),
        ("2026-10-08", "400.1", "2000", "weight_kg"),
        ("2026-10-08", "80", "2000.5", "calories"),
        ("2026-10-08", "80", "abc", "calories"),
        ("2026-10-08", "80", "-1", "calories"),
        ("2026-10-08", "80", "20001", "calories"),
    ],
)
def test_invalid_form(entry_date, weight, calories, field) -> None:
    result = parse_entry_form(entry_date, weight, calories, TODAY)
    assert isinstance(result, EntryFormErrors)
    assert field in result.errors


def test_collects_all_field_errors() -> None:
    result = parse_entry_form("bad date", "bad weight", "bad calories", TODAY)
    assert isinstance(result, EntryFormErrors)
    assert set(result.errors) == {"date", "weight_kg", "calories"}
