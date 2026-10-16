from datetime import date

from tdee_calculator.body_fat import MeasurementRow
from tdee_calculator.calc import DayLog, Sex, Site
from tdee_calculator.logging_calendar import build_calendar, stat_options
from tdee_calculator.settings import Settings
from tdee_calculator.units import EnergyUnit, WeightUnit

TODAY = date(2026, 10, 16)


def test_month_presence_and_exact_past_gaps():
    logs = [
        DayLog(date(2026, 10, 12), 80, None),
        DayLog(date(2026, 10, 13), None, 0),
        DayLog(date(2026, 10, 14), 79.8, 2100),
    ]
    view = build_calendar(logs, [], Settings(), TODAY, TODAY, TODAY)
    cells = {cell.date: cell for week in view.weeks for cell in week if cell}
    assert view.tracking_start == date(2026, 10, 12)
    assert [cell.date.day for cell in view.incomplete] == [12, 13, 15]
    assert [
        cells[date(2026, 10, day)].status for day in [11, 12, 13, 14, 15, 16, 17]
    ] == ["before", "weight", "calories", "both", "missing", "progress", "future"]
    assert cells[date(2026, 10, 13)].values[1].value == "0"


def test_streaks_are_independent_of_view_and_tolerate_unfinished_today():
    logs = [
        DayLog(date(2026, 10, 13), 80, None),
        DayLog(date(2026, 10, 14), 80, 2000),
        DayLog(date(2026, 10, 15), 80, 0),
        DayLog(TODAY, None, 2100),
    ]
    view = build_calendar(logs, [], Settings(), TODAY, date(2026, 9, 1), TODAY, ())
    assert (view.weight_streak.count, view.weight_streak.through) == (
        3,
        date(2026, 10, 15),
    )
    assert (view.calorie_streak.count, view.calorie_streak.through) == (3, TODAY)
    assert view.selected.values == ()
    later = build_calendar(logs, [], Settings(), date(2026, 10, 17), TODAY, TODAY)
    assert later.weight_streak.count == 0
    assert later.calorie_streak.count == 3


def test_measurements_only_do_not_start_daily_tracking_or_borrow_estimates():
    rows = [
        MeasurementRow(date(2026, 10, 10), {Site.NECK: "39.0"}, 18, ""),
        MeasurementRow(TODAY, {Site.NECK: "35.0"}, None, "Needs abdomen"),
    ]
    view = build_calendar(
        [], rows, Settings(sex=Sex.MALE), TODAY, TODAY, TODAY, ("neck", "navy")
    )
    assert view.tracking_start is None
    assert not view.incomplete
    assert view.selected.has_measurements
    assert view.selected.values[0].value == "35.0"
    assert view.selected.values[1].value is None
    assert view.selected.values[1].reason == "Needs abdomen"
    assert view.weight_streak.count == view.calorie_streak.count == 0


def test_profile_options_units_and_hidden_readings():
    profile = Settings(
        sex=Sex.FEMALE, weight_unit=WeightUnit.LB, energy_unit=EnergyUnit.KJ
    )
    assert [option.key for option in stat_options(profile)] == [
        "weight",
        "calories",
        "neck",
        "waist",
        "hip",
        "navy",
    ]
    row = MeasurementRow(TODAY, {Site.ABDOMEN: "34.0", Site.WAIST: "28.0"}, 26, "")
    view = build_calendar(
        [DayLog(TODAY, 81.6466266, 2000)],
        [row],
        profile,
        TODAY,
        TODAY,
        TODAY,
        ("weight", "calories", "abdomen", "waist", "navy"),
    )
    assert [(v.key, v.value, v.unit) for v in view.selected.values] == [
        ("weight", "180.0", "lb"),
        ("calories", "8368", "kJ"),
        ("waist", "28.0", "in"),
        ("navy", "26", "%"),
    ]
    assert row.means[Site.ABDOMEN] == "34.0"
    assert [option.key for option in stat_options(Settings())] == [
        "weight",
        "calories",
        "navy",
    ]


def test_measurement_only_day_keeps_default_daily_values_unknown():
    row = MeasurementRow(TODAY, {Site.NECK: "35.0"}, None, "Needs abdomen")
    view = build_calendar([], [row], Settings(sex=Sex.MALE), TODAY, TODAY, TODAY)
    assert [value.value for value in view.selected.values] == [None, None]


def test_leap_month_padding_and_date_bounds():
    view = build_calendar([], [], Settings(), TODAY, date(2028, 2, 1), TODAY)
    days = [cell.date.day for week in view.weeks for cell in week if cell]
    assert days == list(range(1, 30))
    assert view.weeks[0][0] is None
    assert view.selected.date == TODAY
    assert build_calendar([], [], Settings(), TODAY, date.min, TODAY).previous is None
    assert build_calendar([], [], Settings(), TODAY, date.max, TODAY).next is None


def test_backfill_clear_and_delete_recompute_runs_and_tracking_start():
    logs = [DayLog(date(2026, 10, day), 80, 2000) for day in [13, 15, 16]]
    assert (
        build_calendar(logs, [], Settings(), TODAY, TODAY, TODAY).weight_streak.count
        == 2
    )
    logs.append(DayLog(date(2026, 10, 14), 80, 2000))
    assert (
        build_calendar(logs, [], Settings(), TODAY, TODAY, TODAY).weight_streak.count
        == 4
    )
    logs[-1] = DayLog(date(2026, 10, 14), None, 2000)
    view = build_calendar(logs, [], Settings(), TODAY, TODAY, TODAY)
    assert (view.weight_streak.count, view.calorie_streak.count) == (2, 4)
    logs = [DayLog(TODAY, None, None)]
    assert (
        build_calendar(logs, [], Settings(), TODAY, TODAY, TODAY).tracking_start is None
    )


def test_streak_crosses_year_and_leap_day():
    for days, today in [
        ([date(2025, 12, 31), date(2026, 1, 1)], date(2026, 1, 1)),
        ([date(2028, 2, 28), date(2028, 2, 29), date(2028, 3, 1)], date(2028, 3, 1)),
    ]:
        logs = [DayLog(day, 80, 0) for day in days]
        view = build_calendar(logs, [], Settings(), today, today, today)
        assert view.weight_streak.count == view.calorie_streak.count == len(days)
