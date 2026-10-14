from datetime import date

import pytest
from test_body_fat import FEMALE, FEMALE_SITES, MALE, MALE_SITES, session

from tdee_calculator.calc import Site
from tdee_calculator.measurement_dashboard import build_measurement_dashboard
from tdee_calculator.settings import Settings
from tdee_calculator.units import WeightUnit

TODAY = date(2026, 10, 8)


def test_empty_measurements_have_no_summary_or_cadence():
    result = build_measurement_dashboard([], MALE, TODAY)
    assert result.newest is None
    assert result.latest is None
    assert result.next_suggested is None
    assert result.cadence is None


def test_partial_session_keeps_older_estimate_date_without_filling_missing_sites():
    result = build_measurement_dashboard(
        [session(TODAY, {Site.WAIST: [80]}), session(date(2026, 10, 3), MALE_SITES)],
        MALE,
        TODAY,
    )
    assert result.newest is not None
    assert result.newest.date == TODAY
    assert result.newest.means == {Site.WAIST: "80.0"}
    assert result.newest.reason == "Needs neck and abdomen"
    assert result.latest is not None
    assert result.latest.date == date(2026, 10, 3)
    assert result.latest.estimate == pytest.approx(18, abs=0.5)
    assert result.next_suggested == date(2026, 10, 15)


@pytest.mark.parametrize(
    "today,state",
    [
        (date(2026, 10, 9), "future"),
        (date(2026, 10, 10), "today"),
        (date(2026, 10, 12), "past"),
    ],
)
def test_cadence_is_anchored_to_session_date(today, state):
    result = build_measurement_dashboard(
        [session(date(2026, 10, 3), MALE_SITES)], MALE, today
    )
    assert result.next_suggested == date(2026, 10, 10)
    assert result.cadence == state


@pytest.mark.parametrize(
    "day,next_day",
    [(date(2026, 9, 27), date(2026, 10, 4)), (date(2026, 12, 28), date(2027, 1, 4))],
)
def test_cadence_crosses_week_and_year_boundaries(day, next_day):
    result = build_measurement_dashboard([session(day, {Site.NECK: [35]})], MALE, day)
    assert result.next_suggested == next_day


@pytest.mark.parametrize(
    "settings,sites,reason,needs_settings",
    [
        (Settings(), MALE_SITES, "Set sex and height in Settings", True),
        (
            MALE,
            {Site.NECK: [40], Site.ABDOMEN: [40]},
            "Outside the equation's range",
            False,
        ),
    ],
)
def test_unusable_estimates_keep_readings_and_cadence(
    settings, sites, reason, needs_settings
):
    result = build_measurement_dashboard([session(TODAY, sites)], settings, TODAY)
    assert result.newest is not None
    assert result.newest.means
    assert result.newest.reason == reason
    assert result.newest.needs_settings == needs_settings
    assert result.latest is None
    assert result.next_suggested == date(2026, 10, 15)


@pytest.mark.parametrize("weight", list(WeightUnit))
@pytest.mark.parametrize(
    "settings,sites,expected", [(MALE, MALE_SITES, 18), (FEMALE, FEMALE_SITES, 26)]
)
def test_known_estimates_and_display_units(settings, sites, expected, weight):
    selected = Settings(
        sex=settings.sex, height_cm=settings.height_cm, weight_unit=weight
    )
    result = build_measurement_dashboard([session(TODAY, sites)], selected, TODAY)
    assert result.latest is not None
    assert result.latest.estimate == pytest.approx(expected, abs=0.5)
    assert result.latest.means[Site.NECK] == (
        ("39.4" if expected == 18 else "33.0")
        if weight == WeightUnit.KG
        else ("15.5" if expected == 18 else "13.0")
    )
