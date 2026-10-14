from datetime import date

import pytest

from tdee_calculator.body_fat import build_row, build_summary
from tdee_calculator.calc import Sex, Site
from tdee_calculator.models import MeasurementReading, MeasurementSession
from tdee_calculator.settings import Settings
from tdee_calculator.units import WeightUnit

DAY = date(2026, 10, 8)
INCH = 2.54
# Navy Guide 4 (Mar 2021), Tables 2/3 (see test_calc.py): whole-percent answers.
MALE = Settings(sex=Sex.MALE, height_cm=71 * INCH)
MALE_SITES = {Site.NECK: [15.5 * INCH], Site.ABDOMEN: [35 * INCH]}  # 18%
FEMALE = Settings(sex=Sex.FEMALE, height_cm=65 * INCH)
FEMALE_SITES = {
    Site.NECK: [13 * INCH],
    Site.WAIST: [28 * INCH],
    Site.HIP: [38 * INCH],
}  # 26%


def session(day: date, sites: dict[Site, list[float]]) -> MeasurementSession:
    return MeasurementSession(
        date=day,
        readings=[
            MeasurementReading(site=site.value, reading=slot, value_cm=value)
            for site, values in sites.items()
            for slot, value in enumerate(values, start=1)
        ],
    )


@pytest.mark.parametrize(
    "settings,sites,expected",
    [(MALE, MALE_SITES, 18), (FEMALE, FEMALE_SITES, 26)],
)
def test_estimate_matches_navy_guide_tables(settings, sites, expected):
    row = build_row(session(DAY, sites), settings)
    assert row.date == DAY
    assert row.estimate == pytest.approx(expected, abs=0.5)
    assert row.reason == ""
    assert not row.needs_settings


@pytest.mark.parametrize(
    "settings,reason",
    [
        (Settings(), "Set sex and height in Settings"),
        (Settings(height_cm=180), "Set sex in Settings"),
        (Settings(sex=Sex.MALE), "Set height in Settings"),
    ],
)
def test_missing_settings_keep_means_and_link_to_settings(settings, reason):
    row = build_row(session(DAY, {Site.NECK: [35]}), settings)
    assert row.estimate is None
    assert row.reason == reason
    assert row.needs_settings
    assert row.means == {Site.NECK: "35.0"}


@pytest.mark.parametrize(
    "settings,sites,reason",
    [
        (MALE, {Site.NECK: [40]}, "Needs abdomen"),
        (MALE, {Site.WAIST: [80]}, "Needs neck and abdomen"),
        (FEMALE, {Site.NECK: [33], Site.WAIST: [71]}, "Needs hip"),
        (FEMALE, {Site.ABDOMEN: [90]}, "Needs neck and waist and hip"),
    ],
)
def test_missing_sites_name_what_the_equation_needs(settings, sites, reason):
    row = build_row(session(DAY, sites), settings)
    assert row.estimate is None
    assert row.reason == reason
    assert not row.needs_settings


@pytest.mark.parametrize(
    "sites",
    [
        {Site.NECK: [40], Site.ABDOMEN: [40]},  # log of zero
        {Site.NECK: [40], Site.ABDOMEN: [40.1]},  # far below 2%
        {Site.NECK: [20], Site.ABDOMEN: [250]},  # far above 60%
    ],
)
def test_out_of_range_estimate_is_refused(sites):
    row = build_row(session(DAY, sites), MALE)
    assert row.estimate is None
    assert row.reason == "Outside the equation's range"


def test_means_average_readings_in_the_display_length_unit():
    sites = {Site.ABDOMEN: [86.36, 87.63, 86.36], Site.NECK: [38.1]}
    # (86.36 + 87.63 + 86.36) / 3 = 86.783 cm; 38.1 cm is exactly 15 in.
    assert build_row(session(DAY, sites), MALE).means == {
        Site.NECK: "38.1",
        Site.ABDOMEN: "86.8",
    }
    lb = Settings(sex=Sex.MALE, height_cm=180, weight_unit=WeightUnit.LB)
    assert build_row(session(DAY, sites), lb).means == {
        Site.NECK: "15.0",
        Site.ABDOMEN: "34.2",
    }


def test_summary_latest_is_newest_estimate_and_newer_rows_are_listed():
    sessions = [
        session(date(2026, 10, 8), {Site.WAIST: [80]}),
        session(date(2026, 10, 7), {Site.NECK: [40]}),
        session(date(2026, 10, 6), MALE_SITES),
        session(date(2026, 10, 5), MALE_SITES),
    ]
    summary = build_summary(sessions, MALE)
    assert [row.date for row in summary.rows] == [
        date(2026, 10, 8),
        date(2026, 10, 7),
        date(2026, 10, 6),
        date(2026, 10, 5),
    ]
    assert summary.latest is not None
    assert summary.latest.date == date(2026, 10, 6)
    assert [row.date for row in summary.newer] == [
        date(2026, 10, 8),
        date(2026, 10, 7),
    ]


@pytest.mark.parametrize(
    "sessions",
    [[], [session(DAY, {Site.WAIST: [80]})]],
)
def test_summary_without_any_estimate_has_no_latest(sessions):
    summary = build_summary(sessions, MALE)
    assert summary.latest is None
    assert summary.newer == ()
    assert len(summary.rows) == len(sessions)
