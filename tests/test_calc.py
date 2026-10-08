import ast
from dataclasses import FrozenInstanceError, fields, replace
from datetime import date, timedelta
import inspect
from statistics import mean
import sys

import pytest

from tdee_calculator import calc


START = date(2026, 1, 1)


def make_logs(intakes=None, *, days=28, tdee=2500, density=7700):
    """Simulate daily energy balance; each intake affects the next morning."""
    if intakes is None:
        intakes = [2000] * days
    weight = 80.0
    logs = []
    for index, calories in enumerate(intakes):
        logs.append(calc.DayLog(START + timedelta(days=index), weight, calories))
        weight += (calories - tdee) / density
    logs.append(calc.DayLog(START + timedelta(days=len(intakes)), weight, None))
    return logs


def infer(logs, **kwargs):
    return calc.logged_tdee(logs, START + timedelta(days=28), **kwargs)


def test_calc_imports_only_standard_library_and_does_not_read_the_clock():
    tree = ast.parse(inspect.getsource(calc))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            modules = [node.module]
        else:
            continue
        assert all(module.split(".")[0] in sys.stdlib_module_names for module in modules)
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"now", "today", "utcnow"}
        for node in ast.walk(tree)
    )


def test_inputs_and_results_are_frozen():
    log = make_logs()[0]
    with pytest.raises(FrozenInstanceError):
        log.calories = 3000
    with pytest.raises(FrozenInstanceError):
        infer(make_logs()).tdee = 3000


@pytest.mark.parametrize("field", ["weight_kg", "calories"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_day_log_rejects_non_finite_numbers(field, value):
    with pytest.raises(ValueError):
        calc.DayLog(START, **{"weight_kg": 80.0, "calories": 2000, field: value})


def test_trend_seeds_and_smooths_only_weigh_ins():
    logs = [calc.DayLog(START, 80, None)] + [
        calc.DayLog(START + timedelta(days=i), 81, None) for i in range(1, 4)
    ]
    points = calc.trend(reversed(logs))
    assert [point.trend_kg for point in points] == pytest.approx(
        [80, 80.1, 80.19, 80.271]
    )
    assert [point.weight_kg for point in points] == [80, 81, 81, 81]
    assert [point.date for point in points] == [log.date for log in logs]
    spaced = [replace(log, date=START + timedelta(days=i * 7)) for i, log in enumerate(logs)]
    with_gap = spaced + [calc.DayLog(START + timedelta(days=1), None, 2000)]
    assert [point.trend_kg for point in calc.trend(with_gap)] == pytest.approx(
        [point.trend_kg for point in points]
    )


def test_trend_constant_empty_and_alpha_one():
    assert calc.trend([]) == []
    assert calc.trend([calc.DayLog(START, None, 2000)]) == []
    assert all(point.trend_kg == 80 for point in calc.trend(make_logs(tdee=2000)))
    assert all(point.trend_kg == point.weight_kg for point in calc.trend(make_logs(), 1))


@pytest.mark.parametrize("alpha", [0, -0.1, 1.1, float("nan"), float("inf")])
def test_trend_rejects_invalid_alpha(alpha):
    with pytest.raises(ValueError):
        calc.trend([], alpha)


def test_weight_slope_uses_actual_dates_and_ignores_missing_weights():
    logs = [calc.DayLog(START + timedelta(days=i), 80 - i * 0.1, None) for i in range(29)]
    sparse = [log for i, log in enumerate(logs) if i % 3 == 0]
    sparse.append(calc.DayLog(START + timedelta(days=1), None, 2000))
    assert calc.weight_slope(iter(reversed(sparse))) == pytest.approx(-0.1)


@pytest.mark.parametrize("weights", [[], [80], [None, 80, None]])
def test_weight_slope_needs_two_weigh_ins(weights):
    logs = [calc.DayLog(START + timedelta(days=i), value, None) for i, value in enumerate(weights)]
    assert calc.weight_slope(logs) is None


@pytest.mark.parametrize("tdee", [2550, 1450, 2000])
def test_logged_tdee_known_loss_gain_and_maintenance(tdee):
    result = infer(make_logs(tdee=tdee))
    assert result.tdee == pytest.approx(tdee)
    assert result.slope_kg_per_day == pytest.approx((2000 - tdee) / 7700)
    assert result.avg_intake == 2000
    assert (result.start_date, result.end_date) == (START, START + timedelta(days=28))
    assert (result.span_days, result.weigh_ins, result.calorie_days, result.imputed_days) == (28, 29, 28, 0)
    assert result.calorie_coverage == 1


def test_custom_density_is_used_in_the_energy_balance():
    result = infer(make_logs(density=9000), energy_density=9000)
    assert result.tdee == pytest.approx(2500)
    assert result.slope_kg_per_day == pytest.approx(-500 / 9000)


@pytest.mark.parametrize("sparse", [False, True])
def test_variable_intake_and_irregular_weigh_ins_recover_known_tdee(sparse):
    logs = make_logs([2000] * 10 + [4000] * 7 + [2000] * 11)
    if sparse:
        dates = {0, 3, 6, 9, 12, 15, 18, 21, 24, 28}
        logs = [replace(log, weight_kg=None) if i not in dates else log for i, log in enumerate(logs)]
    result = infer(iter(reversed(logs)))
    assert result.tdee == pytest.approx(2500)
    if not sparse:
        old_estimate = mean(log.calories for log in logs[:-1]) - 7700 * calc.weight_slope(logs)
        assert old_estimate == pytest.approx(2289.6551724)


def test_window_includes_boundary_mornings_and_ignores_old_and_future_logs():
    logs = make_logs()
    extras = [
        calc.DayLog(START - timedelta(days=1), 150, 9000),
        calc.DayLog(START + timedelta(days=29), 20, 10000),
    ]
    assert infer(extras + logs) == infer(logs)
    assert infer(logs).start_date == START


@pytest.mark.parametrize("calories", [None, 500, 10000])
def test_final_morning_calories_do_not_affect_estimate_or_coverage(calories):
    logs = make_logs()
    changed = logs[:-1] + [replace(logs[-1], calories=calories)]
    assert infer(changed) == infer(logs)


def test_interval_ends_at_last_actual_weight_and_starts_at_first_actual_weight():
    logs = make_logs()
    changed = [replace(logs[0], weight_kg=None, calories=9000)] + logs[1:]
    changed[-1] = replace(changed[-1], weight_kg=None, calories=9000)
    changed[-2] = replace(changed[-2], calories=9000)
    result = infer(changed)
    assert result.tdee == pytest.approx(2500)
    assert result.start_date == START + timedelta(days=1)
    assert result.end_date == START + timedelta(days=27)
    assert result.span_days == result.calorie_days == 26
    assert result.avg_intake == 2000


@pytest.mark.parametrize("count,span,eligible", [(9, 21, False), (10, 21, True), (10, 9, False), (10, 20, False)])
def test_minimum_weight_count_and_elapsed_span(count, span, eligible):
    dates = {round(i * span / (count - 1)) for i in range(count)}
    logs = [replace(log, weight_kg=None) if i not in dates else log for i, log in enumerate(make_logs(days=span))]
    result = calc.logged_tdee(logs, START + timedelta(days=span))
    assert (result is not None) is eligible


@pytest.mark.parametrize("span,recorded,eligible", [(28, 25, False), (28, 26, True), (21, 18, False), (21, 19, True)])
def test_calorie_coverage_uses_actual_bracketed_span(span, recorded, eligible):
    logs = make_logs(days=span)
    logs = [replace(log, calories=None) if recorded <= i < span else log for i, log in enumerate(logs)]
    result = calc.logged_tdee(logs, START + timedelta(days=28))
    assert (result is not None) is eligible
    if eligible:
        assert result.tdee == pytest.approx(2500)
        assert result.calorie_days == recorded
        assert result.imputed_days == span - recorded
        assert result.calorie_coverage == pytest.approx(recorded / span)


@pytest.mark.parametrize("recorded,eligible", [(13, False), (14, True)])
def test_custom_coverage_threshold_is_not_raised_by_float_error(recorded, eligible):
    # 0.56 × 25 is 14.000000000000002 in floating point, but 14 of 25 days is exactly 56%.
    logs = make_logs(days=25)
    logs = [replace(log, calories=None) if recorded <= i < 25 else log for i, log in enumerate(logs)]
    result = infer(logs, min_calorie_coverage=0.56)
    assert (result is not None) is eligible


def test_missing_rows_and_unknown_totals_fill_identically_without_mutation():
    logs = make_logs()
    original = logs.copy()
    missing_rows = [log for i, log in enumerate(logs) if i not in {5, 15}]
    unknown_totals = [replace(log, weight_kg=None, calories=None) if i in {5, 15} else log for i, log in enumerate(logs)]
    assert infer(missing_rows) == infer(unknown_totals)
    assert infer(missing_rows).tdee == pytest.approx(2500)
    assert logs == original
    assert unknown_totals[5].calories is None


def test_zero_calories_is_recorded_not_missing():
    result = infer(make_logs([0] + [2000] * 27))
    assert result.tdee == pytest.approx(2500)
    assert result.calorie_days == 28
    assert result.imputed_days == 0
    assert result.avg_intake == pytest.approx(54000 / 28)


def test_missing_high_intake_days_can_bias_an_eligible_estimate():
    complete = make_logs([2000] * 10 + [4000] * 7 + [2000] * 11)
    missing = [replace(log, calories=None) if i in {13, 14} else log for i, log in enumerate(complete)]
    lower = [replace(log, calories=2000) if i in {13, 14} else log for i, log in enumerate(complete)]
    result = infer(missing)
    assert result.calorie_days == 26
    assert result.imputed_days == 2
    assert infer(lower).tdee < result.tdee < 2500
    assert infer(complete).tdee == pytest.approx(2500)


def test_linear_water_loss_biases_tdee_without_claiming_uncertainty():
    logs = [replace(log, weight_kg=log.weight_kg - 0.5 * i / 28) for i, log in enumerate(make_logs())]
    result = infer(logs)
    assert result.tdee == pytest.approx(2637.5)
    assert not {"confidence", "standard_error", "confidence_interval"} & {field.name for field in fields(result)}


@pytest.mark.parametrize("day,expected", [(0, 2553.1034483), (14, 2500), (28, 2446.8965517)])
def test_temporary_water_spike_is_not_removed_by_regression(day, expected):
    logs = make_logs()
    logs[day] = replace(logs[day], weight_kg=logs[day].weight_kg + 1)
    assert infer(logs).tdee == pytest.approx(expected)


def test_constant_underlogging_shifts_inferred_tdee():
    logs = [replace(log, calories=log.calories - 300) if log.calories is not None else log for log in make_logs()]
    assert infer(logs).tdee == pytest.approx(2200)


@pytest.mark.parametrize("kind", ["empty", "no_weights", "no_calories"])
def test_logged_tdee_returns_none_for_insufficient_data(kind):
    logs = make_logs()
    if kind == "empty":
        logs = []
    elif kind == "no_weights":
        logs = [replace(log, weight_kg=None) for log in logs]
    else:
        logs = [replace(log, calories=None) for log in logs]
    assert infer(logs) is None


@pytest.mark.parametrize("kwargs", [
    {"window_days": 0}, {"window_days": -1}, {"window_days": 28.5},
    {"min_span_days": 0}, {"min_span_days": 29}, {"min_span_days": 21.5},
    {"min_weigh_ins": 1}, {"min_weigh_ins": 10.5}, {"min_weigh_ins": True},
    {"energy_density": 0}, {"energy_density": float("inf")}, {"energy_density": float("nan")},
    {"min_calorie_coverage": 0}, {"min_calorie_coverage": 1.1}, {"min_calorie_coverage": float("nan")},
])
def test_logged_tdee_rejects_invalid_parameters_even_without_data(kwargs):
    with pytest.raises(ValueError):
        infer([], **kwargs)


@pytest.mark.parametrize("sex,weight,height,age,expected", [
    (calc.Sex.MALE, 80, 180, 30, 1780),
    (calc.Sex.FEMALE, 60, 165, 25, 1345.25),
    ("female", 60, 165, 25, 1345.25),
])
def test_mifflin_st_jeor_known_answers(sex, weight, height, age, expected):
    assert calc.mifflin_st_jeor_ree(sex, weight, height, age) == pytest.approx(expected)


@pytest.mark.parametrize("activity", list(calc.ActivityLevel))
def test_formula_tdee_multiplies_ree(activity):
    assert calc.formula_tdee(1780, activity) == pytest.approx(1780 * activity.value)


@pytest.mark.parametrize("born,on,expected", [
    (date(1990, 6, 15), date(2026, 6, 14), 35),
    (date(1990, 6, 15), date(2026, 6, 15), 36),
    (date(1990, 6, 15), date(2026, 6, 16), 36),
    (date(2000, 2, 29), date(2025, 2, 28), 24),
    (date(2000, 2, 29), date(2025, 3, 1), 25),
    (date(2000, 2, 29), date(2024, 2, 29), 24),
])
def test_age_on_counts_complete_birthdays(born, on, expected):
    assert calc.age_on(born, on) == expected


def test_age_on_rejects_dates_before_birth():
    with pytest.raises(ValueError):
        calc.age_on(START, START - timedelta(days=1))


@pytest.mark.parametrize("span,share,method", [(21, 0, "formula"), (24, 3 / 7, "blend"), (28, 1, "logs")])
def test_blend_ramp_and_retained_metadata(span, share, method):
    logged = infer(make_logs(days=span))
    result = calc.estimate_tdee(logged, 2000)
    assert result.logs_weight == pytest.approx(share)
    assert result.tdee == pytest.approx(share * 2500 + (1 - share) * 2000)
    assert result.method == method
    assert result.logged is logged
    assert result.formula == 2000


def test_blend_scales_by_coverage_not_eligible_weigh_in_count():
    logs = [replace(log, calories=None) if i in {5, 15} else log for i, log in enumerate(make_logs())]
    full = infer(logs)
    sparse = infer([replace(log, weight_kg=None) if i % 3 and i != 28 else log for i, log in enumerate(logs)])
    assert calc.estimate_tdee(full, 2000).logs_weight == pytest.approx(26 / 28)
    assert calc.estimate_tdee(sparse, 2000).logs_weight == pytest.approx(26 / 28)
    assert calc.estimate_tdee(full, 2000).method == "blend"


def test_blend_missing_estimate_fallbacks():
    assert calc.estimate_tdee(None, None) is None
    formula = calc.estimate_tdee(None, 2000)
    assert (formula.tdee, formula.method, formula.logs_weight, formula.logged) == (2000, "formula", 0, None)
    logged = infer(make_logs(days=21))
    result = calc.estimate_tdee(logged, None)
    assert result.tdee == pytest.approx(2500)
    assert (result.method, result.logs_weight, result.formula) == ("logs", 1, None)


def test_blend_clamps_ramp_and_ignores_fit_noise():
    logged = infer(make_logs())
    assert calc.estimate_tdee(logged, 2000, blend_start_days=30, blend_full_days=40).logs_weight == 0
    assert calc.estimate_tdee(logged, 2000, blend_start_days=0, blend_full_days=7).logs_weight == 1
    noisy = make_logs()
    noisy[0] = replace(noisy[0], weight_kg=81)
    assert calc.estimate_tdee(infer(noisy), 2000).logs_weight == calc.estimate_tdee(logged, 2000).logs_weight
    assert calc.estimate_tdee(infer([]), 2000).logged is None


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_blend_rejects_non_finite_estimates_even_at_zero_share(value):
    # At a 21-day span the logs' share is 0, and 0 × NaN is still NaN.
    logged = infer(make_logs(days=21))
    assert calc.estimate_tdee(logged, 2000).logs_weight == 0
    with pytest.raises(ValueError):
        calc.estimate_tdee(replace(logged, tdee=value), 2000)
    with pytest.raises(ValueError):
        calc.estimate_tdee(logged, value)
    with pytest.raises(ValueError):
        calc.estimate_tdee(None, value)


@pytest.mark.parametrize("kwargs", [
    {"blend_start_days": -1}, {"blend_start_days": 28},
    {"blend_full_days": 20}, {"blend_start_days": 21.5}, {"blend_full_days": True},
])
def test_blend_rejects_invalid_parameters(kwargs):
    with pytest.raises(ValueError):
        calc.estimate_tdee(None, None, **kwargs)


@pytest.mark.parametrize("rate,expected", [(-0.5, 1950), (0.25, 2775), (0, 2500)])
def test_daily_target_sign(rate, expected):
    assert calc.daily_target(2500, rate) == pytest.approx(expected)


def test_daily_target_uses_custom_density():
    assert calc.daily_target(2500, -0.5, 7000) == 2000


@pytest.mark.parametrize("density", [0, -1, float("nan"), float("inf")])
def test_daily_target_rejects_invalid_density(density):
    with pytest.raises(ValueError):
        calc.daily_target(2500, -0.5, density)


def test_goal_eta_loss_gain_and_fractional_day_rounding():
    eta = calc.goal_eta(85, 80, -0.5, START)
    assert (eta.remaining_kg, eta.weeks, eta.date) == (-5, 10, START + timedelta(days=70))
    gain = calc.goal_eta(80, 85, 0.5, START)
    assert (gain.remaining_kg, gain.weeks, gain.date) == (5, 10, START + timedelta(days=70))
    fractional = calc.goal_eta(80, 81, 2, START)
    assert fractional.weeks == 0.5
    assert fractional.date == START + timedelta(days=4)


@pytest.mark.parametrize("current,goal,rate", [(85, 80, 0), (85, 80, 0.5), (80, 85, -0.5)])
def test_goal_eta_requires_progress_toward_goal(current, goal, rate):
    assert calc.goal_eta(current, goal, rate, START) is None


@pytest.mark.parametrize("current", [80, 80.04, 79.96])
def test_goal_eta_already_at_goal_even_without_a_rate(current):
    eta = calc.goal_eta(current, 80, 0, START)
    assert eta.remaining_kg == pytest.approx(80 - current)
    assert eta.weeks == 0
    assert eta.date == START


@pytest.mark.parametrize("current,goal", [
    (80, 80.05), (80.05, 80), (80.1, 80.15), (80.15, 80.1),
])
def test_goal_eta_tolerance_is_inclusive_at_exactly_0_05_in_both_directions(current, goal):
    # 80.15 − 80.1 is 0.05000000000001137 in floating point.
    eta = calc.goal_eta(current, goal, 0, START)
    assert eta is not None
    assert eta.weeks == 0


@pytest.mark.parametrize("current,goal", [(80, 80.051), (80.051, 80)])
def test_goal_eta_tolerance_stays_tight(current, goal):
    assert calc.goal_eta(current, goal, 0, START) is None
