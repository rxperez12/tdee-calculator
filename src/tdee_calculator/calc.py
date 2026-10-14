"""Pure TDEE calculations in kg and kcal, with explicit dates and morning weights.

Logged TDEE assumes locally constant expenditure and tissue energy density. Missing
intake is mean-filled only within the fitted interval; coverage and blend shares
are heuristics, not statistical confidence or protection against water-weight bias.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum, StrEnum
from math import isfinite, log10
from statistics import linear_regression, mean
from typing import Literal


@dataclass(frozen=True)
class DayLog:
    date: date
    weight_kg: float | None
    calories: int | None

    def __post_init__(self) -> None:
        _require_finite(self.weight_kg, "weight_kg")
        _require_finite(self.calories, "calories")


@dataclass(frozen=True)
class TrendPoint:
    date: date
    weight_kg: float
    trend_kg: float


@dataclass(frozen=True)
class LoggedTdee:
    tdee: float
    slope_kg_per_day: float
    avg_intake: float
    start_date: date
    end_date: date
    span_days: int
    weigh_ins: int
    calorie_days: int
    imputed_days: int
    calorie_coverage: float


class Sex(StrEnum):
    MALE = "male"
    FEMALE = "female"


class Site(StrEnum):
    NECK = "neck"
    ABDOMEN = "abdomen"
    WAIST = "waist"
    HIP = "hip"


def mean_reading(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("readings must not be empty")
    for value in values:
        _require_finite(value, "reading")
    return mean(values)


def navy_body_fat(
    sex: Sex, height_cm: float, sites: Mapping[Site, float]
) -> float | None:
    """Traditional Hodgdon-Beckett inch equations; return unrounded percent.

    Raw site means are used without the Navy assessment's half-inch rounding.
    """
    _require_finite(height_cm, "height_cm")
    if height_cm <= 0:
        raise ValueError("height_cm must be positive")
    required = (
        (Site.NECK, Site.ABDOMEN)
        if sex == Sex.MALE
        else (Site.NECK, Site.WAIST, Site.HIP)
    )
    if any(site not in sites for site in required):
        return None
    for site in required:
        _require_finite(sites[site], site.value)
    if sex == Sex.MALE:
        circumference = sites[Site.ABDOMEN] - sites[Site.NECK]
        if circumference <= 0:
            raise ValueError("abdomen must be greater than neck")
        return (
            86.010 * log10(circumference / 2.54)
            - 70.041 * log10(height_cm / 2.54)
            + 36.76
        )
    circumference = sites[Site.WAIST] + sites[Site.HIP] - sites[Site.NECK]
    if circumference <= 0:
        raise ValueError("waist plus hip must be greater than neck")
    return (
        163.205 * log10(circumference / 2.54)
        - 97.684 * log10(height_cm / 2.54)
        - 78.387
    )


class ActivityLevel(Enum):
    SEDENTARY = 1.2
    LIGHT = 1.375
    MODERATE = 1.55
    VERY = 1.725
    EXTRA = 1.9


@dataclass(frozen=True)
class TdeeEstimate:
    tdee: float
    method: Literal["formula", "blend", "logs"]
    logs_weight: float
    logged: LoggedTdee | None
    formula: float | None


@dataclass(frozen=True)
class GoalEta:
    remaining_kg: float
    weeks: float
    date: date


def _require_integer(value: int, name: str, minimum: int) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _require_finite(value: float | None, name: str) -> None:
    if value is not None and not isfinite(value):
        raise ValueError(f"{name} must be finite")


def _require_density(energy_density: float) -> None:
    if not isfinite(energy_density) or energy_density <= 0:
        raise ValueError("energy_density must be positive and finite")


def trend(logs: Iterable[DayLog], alpha: float = 0.1) -> list[TrendPoint]:
    """EWMA per weigh-in, intentionally independent of gaps between observations."""
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in (0, 1]")
    points = []
    smoothed = None
    for log in sorted(logs, key=lambda log: log.date):
        if log.weight_kg is None:
            continue
        smoothed = (
            log.weight_kg
            if smoothed is None
            else smoothed + alpha * (log.weight_kg - smoothed)
        )
        points.append(TrendPoint(log.date, log.weight_kg, smoothed))
    return points


def weight_slope(logs: Iterable[DayLog]) -> float | None:
    """Raw weight regression slope in kg per elapsed calendar day."""
    weights = sorted(
        ((log.date, log.weight_kg) for log in logs if log.weight_kg is not None),
        key=lambda point: point[0],
    )
    if len(weights) < 2:
        return None
    elapsed = [(day - weights[0][0]).days for day, _ in weights]
    return linear_regression(elapsed, [weight for _, weight in weights]).slope


@dataclass(frozen=True)
class WindowProgress:
    weigh_ins: int
    span_days: int
    calorie_days: int
    calorie_days_needed: int


def _bracket(
    logs: Iterable[DayLog], as_of: date, window_days: int
) -> tuple[list[tuple[date, float]], dict[date, int]]:
    """Weigh-ins in the window, and recorded intake between the first and last."""
    lower = as_of - timedelta(days=window_days)
    window = sorted(
        (log for log in logs if lower <= log.date <= as_of),
        key=lambda log: log.date,
    )
    weights = [(log.date, log.weight_kg) for log in window if log.weight_kg is not None]
    if not weights:
        return [], {}
    start, end = weights[0][0], weights[-1][0]
    intake = {
        log.date: log.calories
        for log in window
        if start <= log.date < end and log.calories is not None
    }
    return weights, intake


def window_progress(
    logs: Iterable[DayLog],
    as_of: date,
    *,
    window_days: int = 28,
    min_calorie_coverage: float = 0.9,
) -> WindowProgress:
    """How far the window is toward each of logged_tdee's data requirements."""
    _require_integer(window_days, "window_days", 1)
    if not 0 < min_calorie_coverage <= 1:
        raise ValueError("min_calorie_coverage must be in (0, 1]")
    weights, intake = _bracket(logs, as_of, window_days)
    span = (weights[-1][0] - weights[0][0]).days if weights else 0
    needed = 0
    if span:
        # The same comparison logged_tdee makes, not ceil() of a float product.
        # n = span always qualifies, since coverage is at most 1.
        needed = next(n for n in range(span + 1) if n / span >= min_calorie_coverage)
    return WindowProgress(len(weights), span, len(intake), needed)


def logged_tdee(
    logs: Iterable[DayLog],
    as_of: date,
    *,
    window_days: int = 28,
    energy_density: float = 7700,
    min_weigh_ins: int = 10,
    min_span_days: int = 21,
    min_calorie_coverage: float = 0.9,
) -> LoggedTdee | None:
    """Fit cumulative energy balance between actual morning weigh-ins.

    Both window boundary mornings are eligible. Intake covers [first, last), so
    food on the final morning's date never contributes. Dates must be unique and
    recorded calories must be complete daily totals; None and absent days are
    unknown. The caller supplies these input conventions.
    """
    _require_integer(window_days, "window_days", 1)
    _require_integer(min_span_days, "min_span_days", 1)
    _require_integer(min_weigh_ins, "min_weigh_ins", 2)
    _require_density(energy_density)
    if min_span_days > window_days:
        raise ValueError("min_span_days must not exceed window_days")
    if not 0 < min_calorie_coverage <= 1:
        raise ValueError("min_calorie_coverage must be in (0, 1]")

    weights, intake = _bracket(logs, as_of, window_days)
    if len(weights) < min_weigh_ins:
        return None
    start, end = weights[0][0], weights[-1][0]
    span = (end - start).days
    if span < min_span_days:
        return None
    if len(intake) / span < min_calorie_coverage:
        return None
    avg_intake = mean(intake.values())

    # Index d holds intake through d-1: the starting morning has cumulative 0.
    cumulative = [0.0]
    for day in range(span):
        calories = intake.get(start + timedelta(days=day), avg_intake)
        cumulative.append(cumulative[-1] + calories)
    elapsed = [(day - start).days for day, _ in weights]
    adjusted = [
        weight - cumulative[(day - start).days] / energy_density
        for day, weight in weights
    ]
    return LoggedTdee(
        tdee=-energy_density * linear_regression(elapsed, adjusted).slope,
        slope_kg_per_day=linear_regression(
            elapsed, [weight for _, weight in weights]
        ).slope,
        avg_intake=avg_intake,
        start_date=start,
        end_date=end,
        span_days=span,
        weigh_ins=len(weights),
        calorie_days=len(intake),
        imputed_days=span - len(intake),
        calorie_coverage=len(intake) / span,
    )


def age_on(birth_date: date, on: date) -> int:
    """Whole years; a Feb 29 birthday advances on March 1 in non-leap years."""
    if on < birth_date:
        raise ValueError("on must not precede birth_date")
    birthday_pending = (on.month, on.day) < (birth_date.month, birth_date.day)
    return on.year - birth_date.year - birthday_pending


def mifflin_st_jeor_ree(
    sex: Sex, weight_kg: float, height_cm: float, age: int
) -> float:
    """Resting expenditure in kcal/day; activity is a separate approximation."""
    offset = 5 if Sex(sex) is Sex.MALE else -161
    return 10 * weight_kg + 6.25 * height_cm - 5 * age + offset


def formula_tdee(ree: float, activity: ActivityLevel) -> float:
    return ree * activity.value


def estimate_tdee(
    logged: LoggedTdee | None,
    formula: float | None,
    *,
    blend_start_days: int = 21,
    blend_full_days: int = 28,
) -> TdeeEstimate | None:
    """Heuristic span/coverage blend. The share is not statistical confidence."""
    _require_integer(blend_start_days, "blend_start_days", 0)
    _require_integer(blend_full_days, "blend_full_days", 1)
    if blend_start_days >= blend_full_days:
        raise ValueError("blend_start_days must be less than blend_full_days")
    # Checked up front: a zero share still lets NaN through, since 0 * NaN is NaN.
    _require_finite(formula, "formula")
    if logged is not None:
        _require_finite(logged.tdee, "logged.tdee")
    if logged is None:
        if formula is None:
            return None
        return TdeeEstimate(formula, "formula", 0.0, None, formula)
    if formula is None:
        return TdeeEstimate(logged.tdee, "logs", 1.0, logged, None)

    progress = (logged.span_days - blend_start_days) / (
        blend_full_days - blend_start_days
    )
    ramp = max(0.0, min(1.0, progress))
    share = ramp * logged.calorie_coverage
    method: Literal["formula", "blend", "logs"]
    if share == 1:
        method = "logs"
    elif share > 0:
        method = "blend"
    else:
        method = "formula"
    return TdeeEstimate(
        share * logged.tdee + (1 - share) * formula, method, share, logged, formula
    )


def daily_target(
    tdee: float, rate_kg_per_week: float, energy_density: float = 7700
) -> float:
    """Starting intake target; negative rate means loss, positive means gain."""
    _require_density(energy_density)
    return tdee + rate_kg_per_week * energy_density / 7


def goal_eta(
    current_kg: float, goal_kg: float, rate_kg_per_week: float, today: date
) -> GoalEta | None:
    """Constant-rate projection, with a 0.05 kg goal tolerance and rounded days."""
    remaining = goal_kg - current_kg
    # The 1e-9 absorbs float error, e.g. 80.15 - 80.1 = 0.05000000000001137.
    if abs(remaining) <= 0.05 + 1e-9:
        return GoalEta(remaining, 0.0, today)
    if rate_kg_per_week == 0 or remaining * rate_kg_per_week < 0:
        return None
    weeks = remaining / rate_kg_per_week
    return GoalEta(remaining, weeks, today + timedelta(days=round(weeks * 7)))
