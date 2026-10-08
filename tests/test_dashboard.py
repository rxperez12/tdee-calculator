import inspect
from datetime import date, timedelta

import pytest

from tdee_calculator import calc, dashboard
from tdee_calculator.calc import ActivityLevel, DayLog, Sex, TdeeEstimate
from tdee_calculator.dashboard import (
    EstimateInvalid,
    EstimateLow,
    GoalAway,
    GoalNoRate,
    GoalNoSafeTarget,
    GoalNoWeight,
    GoalOnTrack,
    GoalReached,
    GoalTooSlow,
    NoGoal,
    NoTarget,
    Target,
    TargetBelowFloor,
    build_chart,
    build_dashboard,
    calc_params,
    chart_payload,
    goal_status,
    parse_range,
    target_status,
)
from tdee_calculator.settings import Settings
from tdee_calculator.units import WeightUnit, format_rate

TODAY = date(2026, 10, 8)
BODY = {
    "sex": Sex.FEMALE,
    "height_cm": 165.0,
    "birth_date": date(1990, 10, 8),  # 36 on TODAY
    "activity": ActivityLevel.MODERATE,
}


def linear_logs(days=28, *, start_kg=80.0, kg_per_week=-0.5, calories=2000, end=TODAY):
    """Daily weigh-ins changing at an exact rate, with constant intake."""
    first = end - timedelta(days=days)
    return [
        DayLog(first + timedelta(days=d), start_kg + kg_per_week * d / 7, calories)
        for d in range(days + 1)
    ]


def flat_logs(kg=80.0, days=3):
    return [DayLog(TODAY - timedelta(days=d), kg, None) for d in range(days)]


def estimate(tdee):
    return TdeeEstimate(tdee, "formula", 0.0, None, tdee)


def test_no_logs():
    result = build_dashboard([], Settings(goal_weight_kg=75), TODAY)
    assert not result.has_entries
    assert result.trend_kg is None
    assert result.last_weigh_in is None
    assert result.days_since_weigh_in is None
    assert not result.weigh_in_stale
    assert result.estimate is None
    assert result.rate_kg_per_week is None
    assert result.target == NoTarget()
    assert result.goal == GoalNoWeight(75)
    assert build_dashboard([], Settings(), TODAY).goal == NoGoal()


def test_calorie_only_logs_have_no_estimate_even_with_body_stats():
    logs = [DayLog(TODAY - timedelta(days=d), None, 2000) for d in range(30)]
    result = build_dashboard(logs, Settings(goal_weight_kg=75, **BODY), TODAY)
    assert result.has_entries
    assert result.trend_kg is None
    assert result.formula_tdee is None  # the formula needs a weight
    assert result.estimate is None
    assert result.progress.weigh_ins == 0
    assert result.goal == GoalNoWeight(75)


def test_few_weigh_ins_without_body_stats():
    result = build_dashboard(flat_logs(70.0, days=5), Settings(), TODAY)
    assert result.estimate is None
    assert (result.progress.weigh_ins, result.progress.span_days) == (5, 4)
    assert (result.weigh_ins_needed, result.span_needed) == (10, 21)
    assert result.rate_kg_per_week is None
    assert result.missing_body_stats == (
        "sex",
        "height",
        "birth date",
        "activity level",
    )


def test_formula_estimate_from_trend_weight():
    result = build_dashboard(flat_logs(70.0, days=5), Settings(**BODY), TODAY)
    # 10 * 70 + 6.25 * 165 - 5 * 36 - 161 = 1,390.25, * 1.55 moderate.
    assert result.formula_tdee == pytest.approx(2154.8875, abs=1e-9)
    assert result.estimate is not None
    assert result.estimate.method == "formula"
    assert result.missing_body_stats == ()


def test_roadmap_scenario_from_logs():
    result = build_dashboard(linear_logs(), Settings(), TODAY)
    assert result.estimate is not None
    # 2,000 kcal eaten while losing 0.5 kg/week: 2,000 + 0.5 * 7,700 / 7.
    assert result.estimate.tdee == pytest.approx(2550, abs=1e-6)
    assert result.estimate.method == "logs"
    assert result.rate_kg_per_week == pytest.approx(-0.5, abs=1e-9)
    assert result.progress == calc.WindowProgress(29, 28, 28, 26)


@pytest.mark.parametrize(
    "window,expected", [(14, (11, 11, 14)), (28, (21, 21, 28)), (56, (42, 42, 56))]
)
def test_calc_params_follow_the_window(window, expected):
    assert calc_params(window) == expected


@pytest.mark.parametrize(
    "days,method,share", [(21, "formula", 0), (24, "blend", 3 / 7)]
)
def test_blend_ramps_between_span_thresholds(days, method, share):
    result = build_dashboard(linear_logs(days), Settings(**BODY), TODAY)
    assert result.estimate is not None
    assert result.estimate.method == method
    assert result.estimate.logs_weight == pytest.approx(share, abs=1e-9)


@pytest.mark.parametrize(
    "rate,expected",
    [(-0.5, Target(2000)), (None, NoTarget()), (0, Target(2550)), (0.25, Target(2825))],
)
def test_target_follows_rate(rate, expected):
    result = target_status(estimate(2550), Settings(rate_kg_per_week=rate))
    assert result == expected


def test_target_below_floor_suggests_truncated_safe_rate():
    settings = Settings(sex=Sex.FEMALE, rate_kg_per_week=-0.75)
    result = target_status(estimate(2000), settings)
    assert isinstance(result, TargetBelowFloor)
    # 2,000 - 0.75 * 1,100 = 1,175, under 1,200.
    assert result.target == pytest.approx(1175, abs=1e-9)
    assert result.floor == 1200
    # (1,200 - 2,000) * 7 / 7,700 = -0.7272...: truncated to -0.72 (1,208 kcal);
    # nearest rounding would give -0.73, which is 1,197 kcal.
    assert result.safe_rate_kg_per_week == pytest.approx(-0.72, abs=1e-12)
    assert calc.daily_target(2000, result.safe_rate_kg_per_week) >= 1200


def test_safe_rate_is_truncated_in_pounds():
    settings = Settings(
        sex=Sex.FEMALE, rate_kg_per_week=-0.75, weight_unit=WeightUnit.LB
    )
    result = target_status(estimate(2000), settings)
    assert isinstance(result, TargetBelowFloor)
    # -0.7272... kg is -1.6033... lb, truncated to -1.60 lb.
    assert format_rate(result.safe_rate_kg_per_week, WeightUnit.LB) == "-1.60"
    assert calc.daily_target(2000, result.safe_rate_kg_per_week) >= 1200


@pytest.mark.parametrize("sex", [Sex.MALE, None])
def test_male_and_unknown_sex_use_higher_floor(sex):
    result = target_status(estimate(2000), Settings(sex=sex, rate_kg_per_week=-0.5))
    assert isinstance(result, TargetBelowFloor)
    assert result.floor == 1500


def test_target_exactly_at_floor_is_allowed():
    # 0.5 * 11,200 / 7 = 800 exactly, so the target is exactly 1,200.
    settings = Settings(sex=Sex.FEMALE, rate_kg_per_week=-0.5, energy_density=11200)
    assert target_status(estimate(2000), settings) == Target(1200)


@pytest.mark.parametrize("rate", [-1.5, 0, 0.1, None])
def test_low_estimate_never_becomes_a_target(rate):
    # 10 * 40 + 6.25 * 140 - 5 * 80 - 161 = 714, * 1.2 sedentary.
    settings = Settings(sex=Sex.FEMALE, rate_kg_per_week=rate)
    assert target_status(estimate(856.8), settings) == EstimateLow(856.8, 1200)


def test_safe_rate_rounding_to_zero_counts_as_low_estimate():
    # (1,200 - 1,205) * 7 / 7,700 = -0.0045, which truncates to 0.00.
    settings = Settings(sex=Sex.FEMALE, rate_kg_per_week=-0.5)
    assert target_status(estimate(1205), settings) == EstimateLow(1205, 1200)


@pytest.mark.parametrize("rate", [-0.5, 0.25, None])
def test_negative_estimate_is_invalid(rate):
    # Gaining 8 kg in 28 days on 2,000 kcal: 2,000 - (8 / 28) * 7,700 = -200.
    logs = linear_logs(kg_per_week=2.0)
    settings = Settings(rate_kg_per_week=rate, goal_weight_kg=70)
    result = build_dashboard(logs, settings, TODAY)
    assert isinstance(result.target, EstimateInvalid)
    assert result.target.tdee == pytest.approx(-200, abs=1e-6)
    if rate is not None and rate < 0:
        assert isinstance(result.goal, GoalNoSafeTarget)
    assert build_chart(result, settings, "3m").projection == ()


def test_tiny_rate_is_too_slow_instead_of_overflowing():
    # 5 kg at 0.00001 kg/week is 500,000 weeks, past the year 9999.
    settings = Settings(goal_weight_kg=75, rate_kg_per_week=-0.00001)
    result = build_dashboard(flat_logs(), settings, TODAY)
    assert result.goal == GoalTooSlow(75, -5)


@pytest.mark.parametrize("rate,expected", [(-0.01, GoalOnTrack), (-0.009, GoalTooSlow)])
def test_ten_year_eta_limit(rate, expected):
    # 5 / 0.01 = 500 weeks; 5 / 0.009 ~ 556 weeks.
    settings = Settings(goal_weight_kg=75, rate_kg_per_week=rate)
    assert isinstance(goal_status(80, NoTarget(), settings, TODAY), expected)


@pytest.mark.parametrize(
    "trend_kg,goal,rate,target,expected",
    [
        (80, None, -0.5, NoTarget(), NoGoal()),
        (None, 75, -0.5, NoTarget(), GoalNoWeight(75)),
        (75.04, 75, -0.5, NoTarget(), GoalReached(75)),
        (80, 75, None, NoTarget(), GoalNoRate(75, -5)),
        (80, 75, 0, NoTarget(), GoalNoRate(75, -5)),
        (80, 85, -0.5, NoTarget(), GoalAway(85, 5)),
        (80, 75, 0.5, NoTarget(), GoalAway(75, -5)),
        (80, 75, -0.5, TargetBelowFloor(900, 1200, -0.3), GoalNoSafeTarget(75, -5)),
        (80, 75, -0.5, EstimateLow(900, 1200), GoalNoSafeTarget(75, -5)),
    ],
)
def test_goal_states(trend_kg, goal, rate, target, expected):
    settings = Settings(goal_weight_kg=goal, rate_kg_per_week=rate)
    assert goal_status(trend_kg, target, settings, TODAY) == expected


@pytest.mark.parametrize(
    "trend_kg,goal,rate,eta_date",
    [
        (80, 75, -0.5, date(2026, 12, 17)),  # 10 weeks = 70 days
        (70, 72, 0.25, date(2026, 12, 3)),  # 8 weeks = 56 days
    ],
)
def test_goal_on_track_for_loss_and_gain(trend_kg, goal, rate, eta_date):
    settings = Settings(goal_weight_kg=goal, rate_kg_per_week=rate)
    result = goal_status(trend_kg, Target(2000), settings, TODAY)
    assert isinstance(result, GoalOnTrack)
    assert result.eta.date == eta_date


def test_stale_weigh_in():
    logs = [DayLog(TODAY - timedelta(days=5), 80.0, None), DayLog(TODAY, None, 2000)]
    result = build_dashboard(logs, Settings(), TODAY)
    assert result.last_weigh_in == date(2026, 10, 3)
    assert result.days_since_weigh_in == 5
    assert result.weigh_in_stale


def wavy_logs(days=120):
    return [
        DayLog(TODAY - timedelta(days=d), 80.0 + (d % 3) - d * 0.02, None)
        for d in reversed(range(days))
    ]


def test_trend_is_computed_over_all_logs_then_sliced():
    result = build_dashboard(wavy_logs(), Settings(), TODAY)
    recent = build_chart(result, Settings(), "4w").points
    everything = {
        point.date: point for point in build_chart(result, Settings(), "all").points
    }
    first = recent[0]
    assert first.date == TODAY - timedelta(days=28)
    assert first.trend_kg == everything[first.date].trend_kg
    # Restarting the trend at the range start would make it equal the weigh-in.
    assert first.trend_kg != first.weight_kg


@pytest.mark.parametrize(
    "rng,first_days_ago,days",
    [("all", 200, 200), ("all", 3, 28), ("3m", 3, 91), ("4w", 3, 28)],
)
def test_range_lengths(rng, first_days_ago, days):
    result = build_dashboard(flat_logs(days=first_days_ago + 1), Settings(), TODAY)
    chart = build_chart(result, Settings(), rng)
    assert chart.range_days == days
    assert chart.start == TODAY - timedelta(days=days)


def on_track_chart(goal, rate, rng="3m"):
    settings = Settings(goal_weight_kg=goal, rate_kg_per_week=rate)
    result = build_dashboard(flat_logs(), settings, TODAY)
    assert isinstance(result.goal, GoalOnTrack)
    return build_chart(result, settings, rng)


def test_projection_is_capped_at_a_quarter_of_the_range():
    chart = on_track_chart(75, -0.5)
    # 91 // 4 = 22 days at 0.5 kg/week: 80 - 0.5 * 22 / 7.
    assert chart.projection[0] == (TODAY, 80)
    assert chart.projection[1][0] == TODAY + timedelta(days=22)
    assert chart.projection[1][1] == pytest.approx(80 - 0.5 * 22 / 7, abs=1e-9)
    assert chart.end == TODAY + timedelta(days=22)
    assert on_track_chart(75, -0.5, "4w").projection[1][0] == TODAY + timedelta(7)


def test_projection_ends_on_the_goal_when_it_comes_first():
    chart = on_track_chart(79.5, -0.5)  # one week away
    assert chart.projection[1] == (TODAY + timedelta(days=7), 79.5)


@pytest.mark.parametrize("goal,rate", [(79.88, -1.5), (80.12, 1.0)])
def test_projection_does_not_overshoot_rounded_eta(goal, rate):
    # 0.12 kg at 1.5 kg/week is 0.56 days, rounded to tomorrow; a full day at
    # that rate would end at 79.79, past the goal.
    chart = on_track_chart(goal, rate)
    assert chart.projection[1] == (TODAY + timedelta(days=1), goal)


def test_no_projection_when_eta_is_today():
    # 0.06 kg at 1.5 kg/week is 0.28 days, which rounds to today.
    chart = on_track_chart(79.94, -1.5)
    assert chart.projection == ()
    assert chart.end == TODAY


def test_projection_only_when_on_track():
    settings = Settings(goal_weight_kg=85, rate_kg_per_week=-0.5)
    result = build_dashboard(flat_logs(), settings, TODAY)
    assert isinstance(result.goal, GoalAway)
    assert build_chart(result, settings, "3m").projection == ()


def test_range_without_weigh_ins_is_empty_but_stats_remain():
    logs = flat_logs(days=5)
    old = [DayLog(log.date - timedelta(days=100), log.weight_kg, None) for log in logs]
    result = build_dashboard(old, Settings(), TODAY)
    assert result.trend_kg == 80
    chart = build_chart(result, Settings(), "3m")
    assert chart.empty
    assert chart.has_weigh_ins
    assert not build_chart(result, Settings(), "all").empty
    nothing = build_chart(build_dashboard([], Settings(), TODAY), Settings(), "all")
    assert nothing.empty
    assert not nothing.has_weigh_ins


def test_payload_in_pounds():
    settings = Settings(
        weight_unit=WeightUnit.LB, goal_weight_kg=75, rate_kg_per_week=-0.5
    )
    result = build_dashboard(flat_logs(), settings, TODAY)
    payload = chart_payload(build_chart(result, settings, "4w"), WeightUnit.LB)
    assert payload["unit"] == "lb"
    assert payload["start"] == "2026-09-10"
    assert payload["end"] == "2026-10-15"
    # 80 kg = 176.37 lb; 75 kg = 165.35 lb, each shown to 0.1.
    assert payload["weighIns"][-1] == {"x": "2026-10-08", "y": 176.4}
    assert payload["trend"][-1] == {"x": "2026-10-08", "y": 176.4}
    assert payload["goal"] == 165.3
    assert payload["projection"][0] == {"x": "2026-10-08", "y": 176.4}
    assert chart_payload(build_chart(result, settings, "4w"), WeightUnit.KG)[
        "goal"
    ] == pytest.approx(75, abs=1e-9)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("4w", "4w"),
        ("3m", "3m"),
        ("all", "all"),
        (None, "3m"),
        ("", "3m"),
        ("1y", "3m"),
    ],
)
def test_parse_range(text, expected):
    assert parse_range(text) == expected


def test_min_weigh_ins_matches_calc_default():
    default = inspect.signature(calc.logged_tdee).parameters["min_weigh_ins"].default
    assert default == dashboard.MIN_WEIGH_INS
