from dataclasses import replace
from datetime import date

import pytest

from tdee_calculator.calc import ActivityLevel, Sex
from tdee_calculator.settings import Settings
from tdee_calculator.settings_form import (
    SettingsFormErrors,
    parse_settings_form,
    parse_units_form,
    settings_to_form,
)
from tdee_calculator.units import EnergyUnit, WeightUnit

TODAY = date(2026, 10, 8)


def test_metric_form():
    result = parse_settings_form(
        {
            "sex": "female",
            "activity": "MODERATE",
            "height_cm": "177.8",
            "birth_date": "1990-02-03",
            "goal_weight": "75.25",
            "rate_per_week": "-0.5",
            "tdee_window_days": "35",
            "energy_density": "7716.17",
        },
        Settings(),
        TODAY,
    )
    assert result == Settings(
        sex=Sex.FEMALE,
        activity=ActivityLevel.MODERATE,
        height_cm=177.8,
        birth_date=date(1990, 2, 3),
        goal_weight_kg=75.25,
        rate_kg_per_week=-0.5,
        tdee_window_days=35,
        energy_density=7716.17,
    )


def test_imperial_form():
    settings = Settings(weight_unit=WeightUnit.LB, energy_unit=EnergyUnit.KJ)
    result = parse_settings_form(
        {
            "height_ft": "5",
            "height_in": "10",
            "goal_weight": "180",
            "rate_per_week": "-1",
            "energy_density": "14644",
        },
        settings,
        TODAY,
    )
    assert isinstance(result, Settings)
    assert result.height_cm == pytest.approx(177.8, abs=1e-9)
    assert result.goal_weight_kg == pytest.approx(81.6466266, abs=1e-9)
    assert result.rate_kg_per_week == pytest.approx(-0.45359237, abs=1e-9)
    assert result.energy_density == pytest.approx(7716.17, abs=0.01)


@pytest.mark.parametrize("weight", list(WeightUnit))
@pytest.mark.parametrize("energy", list(EnergyUnit))
def test_unchanged_form_preserves_every_canonical_value(weight, energy):
    settings = Settings(
        weight_unit=weight,
        energy_unit=energy,
        sex=Sex.MALE,
        activity=ActivityLevel.LIGHT,
        height_cm=182.8,
        birth_date=date(1990, 1, 1),
        goal_weight_kg=81.7,
        rate_kg_per_week=-0.45359237,
        energy_density=7716.17,
        tdee_window_days=35,
    )
    form = settings_to_form(settings)
    assert parse_settings_form(form, settings, TODAY) == settings
    form["goal_weight"] = "175" if weight is WeightUnit.LB else "75"
    result = parse_settings_form(form, settings, TODAY)
    assert isinstance(result, Settings)
    assert result == replace(
        settings,
        goal_weight_kg=pytest.approx(
            79.37866475 if weight is WeightUnit.LB else 75, abs=1e-9
        ),
    )


def test_clearing_values_and_resetting_advanced():
    settings = Settings(
        sex=Sex.MALE,
        height_cm=180,
        birth_date=date(1990, 1, 1),
        activity=ActivityLevel.LIGHT,
        goal_weight_kg=75,
        rate_kg_per_week=-0.5,
        tdee_window_days=35,
        energy_density=8000,
    )
    assert parse_settings_form({}, settings, TODAY) == Settings()
    assert settings_to_form(Settings())["tdee_window_days"] == ""
    assert settings_to_form(Settings())["energy_density"] == ""


@pytest.mark.parametrize(
    "field,value",
    [
        ("sex", "other"),
        ("activity", "other"),
        ("height_cm", "99"),
        ("height_cm", "251"),
        ("height_cm", "nan"),
        ("height_cm", "bad"),
        ("goal_weight", "19.9"),
        ("goal_weight", "400.1"),
        ("goal_weight", "inf"),
        ("rate_per_week", "-1.51"),
        ("rate_per_week", "1.01"),
        ("rate_per_week", "bad"),
        ("rate_per_week", "nan"),
        ("energy_density", "3999"),
        ("energy_density", "9501"),
        ("energy_density", "bad"),
        ("energy_density", "inf"),
        ("tdee_window_days", "13"),
        ("tdee_window_days", "57"),
        ("tdee_window_days", "28.5"),
        ("birth_date", "2011-10-09"),
        ("birth_date", "2026-10-09"),
        ("birth_date", "1925-10-08"),
        ("birth_date", "bad"),
    ],
)
def test_invalid_fields(field, value):
    result = parse_settings_form({field: value}, Settings(), TODAY)
    assert isinstance(result, SettingsFormErrors)
    assert field in result.errors


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("goal_weight", "44.1", 20),
        ("goal_weight", "881.8", 400),
        ("rate_per_week", "-3.310", -1.5),
        ("rate_per_week", "2.20", 1),
        ("energy_density", "1814", 4000),
        ("energy_density", "4309", 9500),
    ],
)
def test_displayed_bounds_store_exact_bound(field, value, expected):
    result = parse_settings_form(
        {field: value}, Settings(weight_unit=WeightUnit.LB), TODAY
    )
    assert isinstance(result, Settings)
    attr = {
        "goal_weight": "goal_weight_kg",
        "rate_per_week": "rate_kg_per_week",
        "energy_density": "energy_density",
    }[field]
    assert getattr(result, attr) == expected


@pytest.mark.parametrize(
    "field,value",
    [
        ("goal_weight", "44.0"),
        ("goal_weight", "44.05"),
        ("goal_weight", "881.9"),
        ("rate_per_week", "-3.32"),
        ("rate_per_week", "-3.308"),
        ("rate_per_week", "2.21"),
        ("energy_density", "1813"),
        ("energy_density", "4310"),
    ],
)
def test_imperial_values_outside_bounds_are_rejected(field, value):
    result = parse_settings_form(
        {field: value}, Settings(weight_unit=WeightUnit.LB), TODAY
    )
    assert isinstance(result, SettingsFormErrors)
    assert field in result.errors


@pytest.mark.parametrize(
    "feet,inches",
    [
        ("5", "12"),
        ("-1", "0"),
        ("9", "0"),
        ("5", ""),
        ("", "10"),
        ("bad", "10"),
        ("5", "nan"),
        ("3", "0"),
    ],
)
def test_invalid_imperial_height(feet, inches):
    result = parse_settings_form(
        {"height_ft": feet, "height_in": inches},
        Settings(weight_unit=WeightUnit.LB),
        TODAY,
    )
    assert isinstance(result, SettingsFormErrors)
    assert "height" in result.errors


@pytest.mark.parametrize(
    "fields,expected",
    [
        ({"height_cm": "100"}, 100),
        ({"height_cm": "250"}, 250),
        ({"height_ft": "8", "height_in": "2.5"}, 250),
        ({"height_ft": "3", "height_in": "3.5"}, 100),
    ],
)
def test_height_bounds(fields, expected):
    settings = Settings(
        weight_unit=WeightUnit.LB if "height_ft" in fields else WeightUnit.KG
    )
    result = parse_settings_form(fields, settings, TODAY)
    assert isinstance(result, Settings)
    assert result.height_cm == expected


@pytest.mark.parametrize("birthday", ["2011-10-08", "1926-10-08"])
def test_birth_date_age_bounds(birthday):
    result = parse_settings_form({"birth_date": birthday}, Settings(), TODAY)
    assert isinstance(result, Settings)
    assert result.birth_date.isoformat() == birthday


def test_units_only_change_units_and_collect_errors():
    settings = Settings(height_cm=177.8, goal_weight_kg=81.7)
    assert parse_units_form(
        {"weight_unit": "lb", "energy_unit": "kJ"}, settings
    ) == replace(settings, weight_unit=WeightUnit.LB, energy_unit=EnergyUnit.KJ)
    result = parse_units_form({"weight_unit": "bad", "energy_unit": "bad"}, settings)
    assert isinstance(result, SettingsFormErrors)
    assert set(result.errors) == {"weight_unit", "energy_unit"}


@pytest.mark.parametrize(
    "field,value,attribute,expected",
    [
        ("goal_weight", "20", "goal_weight_kg", 20),
        ("goal_weight", "400", "goal_weight_kg", 400),
        ("rate_per_week", "-1.5", "rate_kg_per_week", -1.5),
        ("rate_per_week", "1", "rate_kg_per_week", 1),
        ("tdee_window_days", "14", "tdee_window_days", 14),
        ("tdee_window_days", "56", "tdee_window_days", 56),
        ("energy_density", "4000", "energy_density", 4000),
        ("energy_density", "9500", "energy_density", 9500),
    ],
)
def test_metric_numeric_bounds(field, value, attribute, expected):
    result = parse_settings_form({field: value}, Settings(), TODAY)
    assert isinstance(result, Settings)
    assert getattr(result, attribute) == expected


@pytest.mark.parametrize(
    "weight,value,expected",
    [
        (WeightUnit.KG, "16736", 4000),
        (WeightUnit.KG, "39748", 9500),
        (WeightUnit.LB, "7591", 4000),
        (WeightUnit.LB, "18029", 9500),
    ],
)
def test_kilojoule_density_bounds(weight, value, expected):
    result = parse_settings_form(
        {"energy_density": value},
        Settings(weight_unit=weight, energy_unit=EnergyUnit.KJ),
        TODAY,
    )
    assert isinstance(result, Settings)
    assert result.energy_density == expected


def test_clearing_imperial_height():
    current = Settings(weight_unit=WeightUnit.LB, height_cm=177.8)
    result = parse_settings_form({"height_ft": "", "height_in": ""}, current, TODAY)
    assert isinstance(result, Settings)
    assert result.height_cm is None
