from datetime import date

import pytest

from tdee_calculator.calc import Site
from tdee_calculator.measurement_form import (
    READING_LIMITS,
    MeasurementFormErrors,
    MeasurementInput,
    parse_measurement_form,
)
from tdee_calculator.models import MeasurementReading, MeasurementSession
from tdee_calculator.units import WeightUnit, format_length, length_unit_for

DAY = date(2026, 10, 8)


def parse(**values):
    return parse_measurement_form({"date": str(DAY), **values}, DAY, WeightUnit.KG)


def test_independent_readings_skip_blanks_and_compact_gaps():
    assert parse(neck_2=" 35.25 ", neck_3="36", waist_1="80") == MeasurementInput(
        DAY, {Site.NECK: (35.25, 36), Site.WAIST: (80,)}
    )


@pytest.mark.parametrize("day", ["", "invalid", "2026-10-09"])
def test_invalid_or_future_date(day):
    result = parse(date=day, neck_1="35")
    assert isinstance(result, MeasurementFormErrors)
    assert "date" in result.errors


def test_no_readings():
    result = parse(neck_1=" ")
    assert isinstance(result, MeasurementFormErrors)
    assert result.errors == {"form": "Enter at least one reading."}


@pytest.mark.parametrize("site", list(Site))
@pytest.mark.parametrize("weight", list(WeightUnit))
@pytest.mark.parametrize("bound_index", [0, 1])
def test_displayed_limits_store_exact_canonical_bound(site, weight, bound_index):
    bound = READING_LIMITS[site][bound_index]
    text = format_length(bound, length_unit_for(weight))
    result = parse_measurement_form({"date": str(DAY), f"{site}_1": text}, DAY, weight)
    assert result == MeasurementInput(DAY, {site: (bound,)})


@pytest.mark.parametrize("text", ["invalid", "nan", "inf", "-inf", "19.9", "80.1"])
def test_invalid_reading(text):
    result = parse(neck_1=text)
    assert isinstance(result, MeasurementFormErrors)
    assert "neck_1" in result.errors


@pytest.mark.parametrize("weight", list(WeightUnit))
def test_unchanged_slots_preserve_precision_before_gap_renumbering(weight):
    value = 39.37007874015748
    current = MeasurementSession(
        date=DAY,
        readings=[MeasurementReading(site="neck", reading=2, value_cm=value)],
    )
    result = parse_measurement_form(
        {"date": str(DAY), "neck_2": format_length(value, length_unit_for(weight))},
        DAY,
        weight,
        current,
    )
    assert result == MeasurementInput(DAY, {Site.NECK: (value,)})


def test_imperial_conversion_and_changed_value():
    result = parse_measurement_form(
        {"date": str(DAY), "neck_1": "15.5"}, DAY, WeightUnit.LB
    )
    assert isinstance(result, MeasurementInput)
    assert result.readings[Site.NECK][0] == pytest.approx(39.37, abs=1e-9)


def test_current_slot_can_be_cleared_and_changed():
    current = MeasurementSession(
        date=DAY,
        readings=[MeasurementReading(site="neck", reading=1, value_cm=39.371)],
    )
    assert parse_measurement_form(
        {"date": str(DAY), "neck_1": "40", "waist_1": "80"},
        DAY,
        WeightUnit.KG,
        current,
    ) == MeasurementInput(DAY, {Site.NECK: (40,), Site.WAIST: (80,)})
