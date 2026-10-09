"""The Today page's view model: runs calc and decides what each part shows.

Pure, like calc.py: no database, clock, or web imports, and today is passed in. Values
stay in kg and kcal except in the chart payload, which is in display units.
"""

from dataclasses import dataclass
from datetime import date as Date
from datetime import timedelta
from math import trunc
from typing import Literal

from tdee_calculator import calc
from tdee_calculator.calc import DayLog, GoalEta, Sex, TdeeEstimate, TrendPoint
from tdee_calculator.settings import Settings
from tdee_calculator.units import WeightUnit, weight_from_kg, weight_to_kg

Range = Literal["4w", "3m", "all"]
RANGES: tuple[Range, ...] = ("4w", "3m", "all")
DEFAULT_RANGE: Range = "3m"
RANGE_DAYS: dict[Range, int] = {"4w": 28, "3m": 91}
RANGE_LABELS: dict[Range, str] = {
    "4w": "4 weeks",
    "3m": "3 months",
    "all": "All",
}
MIN_RANGE_DAYS = 28
MIN_AXIS_DAYS = 7

# Must match calc.logged_tdee's default; a test ties them together.
MIN_WEIGH_INS = 10
STALE_WEIGH_IN_DAYS = 3
MAX_ETA_WEEKS = 520
# Below this the actual rate reads as "no significant change". A fixed threshold for
# now; the projection-range work could replace it with the slope's uncertainty.
STEADY_KG_PER_WEEK = 0.1

Movement = Literal["toward", "away", "steady"]

# An application guardrail, not medical advice: never suggest eating less than this.
MIN_INTAKE_KCAL = {Sex.FEMALE: 1200, Sex.MALE: 1500}
MIN_INTAKE_UNKNOWN_SEX = 1500


@dataclass(frozen=True)
class NoTarget:
    """No estimate yet, or an estimate without a rate."""


@dataclass(frozen=True)
class EstimateInvalid:
    tdee: float


@dataclass(frozen=True)
class EstimateLow:
    tdee: float
    floor: int


@dataclass(frozen=True)
class Target:
    kcal: float


@dataclass(frozen=True)
class TargetBelowFloor:
    target: float  # kept for tests; never rendered
    floor: int
    safe_rate_kg_per_week: float


TargetStatus = NoTarget | EstimateInvalid | EstimateLow | Target | TargetBelowFloor


@dataclass(frozen=True)
class NoGoal:
    pass


@dataclass(frozen=True)
class GoalNoWeight:
    goal_kg: float


@dataclass(frozen=True)
class GoalReached:
    goal_kg: float


@dataclass(frozen=True)
class GoalNoRate:
    goal_kg: float
    remaining_kg: float


@dataclass(frozen=True)
class GoalAway:
    goal_kg: float
    remaining_kg: float


@dataclass(frozen=True)
class GoalNoSafeTarget:
    goal_kg: float
    remaining_kg: float


@dataclass(frozen=True)
class GoalTooSlow:
    goal_kg: float
    remaining_kg: float


@dataclass(frozen=True)
class GoalOnTrack:
    goal_kg: float
    eta: GoalEta


GoalStatus = (
    NoGoal
    | GoalNoWeight
    | GoalReached
    | GoalNoRate
    | GoalAway
    | GoalNoSafeTarget
    | GoalTooSlow
    | GoalOnTrack
)


@dataclass(frozen=True)
class Dashboard:
    today: Date
    has_entries: bool
    trend: tuple[TrendPoint, ...]  # over all logs; the chart slices it
    rate_kg_per_week: float | None  # None until the rate gate is met
    estimate: TdeeEstimate | None
    progress: calc.WindowProgress
    weigh_ins_needed: int
    span_needed: int
    full_logs_days: int  # span at which a blend becomes fully log-based
    formula_tdee: float | None
    missing_body_stats: tuple[str, ...]
    target: TargetStatus
    goal: GoalStatus

    @property
    def trend_kg(self) -> float | None:
        return self.trend[-1].trend_kg if self.trend else None

    @property
    def last_weigh_in(self) -> Date | None:
        return self.trend[-1].date if self.trend else None

    @property
    def days_since_weigh_in(self) -> int | None:
        last = self.last_weigh_in
        return None if last is None else (self.today - last).days

    @property
    def weigh_in_stale(self) -> bool:
        days = self.days_since_weigh_in
        return days is not None and days >= STALE_WEIGH_IN_DAYS

    @property
    def trend_early(self) -> bool:
        """Too few weigh-ins for the smoothed trend to have settled."""
        return 0 < len(self.trend) < self.weigh_ins_needed

    @property
    def estimate_early(self) -> bool:
        """The estimate still leans on the formula because the logs are short.

        A blend that is only partial because a few calorie days are missing is not
        early: its span is complete, and the tile already counts estimated days.
        """
        estimate = self.estimate
        if estimate is None or estimate.method == "logs":
            return False
        return (
            estimate.logged is None or estimate.logged.span_days < self.full_logs_days
        )

    @property
    def days_to_full_logs(self) -> int | None:
        estimate = self.estimate
        if not self.estimate_early or estimate is None or estimate.logged is None:
            return None
        return self.full_logs_days - estimate.logged.span_days

    @property
    def goal_remaining_kg(self) -> float | None:
        goal = self.goal
        if isinstance(goal, GoalOnTrack):
            return goal.eta.remaining_kg
        if isinstance(goal, GoalNoRate | GoalAway | GoalNoSafeTarget | GoalTooSlow):
            return goal.remaining_kg
        return None

    @property
    def movement(self) -> Movement | None:
        """Which way the actual rate is moving relative to the goal."""
        rate, remaining = self.rate_kg_per_week, self.goal_remaining_kg
        if rate is None or remaining is None:
            return None
        if abs(rate) < STEADY_KG_PER_WEEK:
            return "steady"
        return "toward" if rate * remaining > 0 else "away"


def calc_params(window_days: int) -> tuple[int, int, int]:
    """min_span_days, blend_start_days, blend_full_days for a TDEE window."""
    min_span = (3 * window_days + 3) // 4  # ceil(window * 3/4) in integers
    return min_span, min_span, window_days


def intake_floor(sex: Sex | None) -> int:
    return MIN_INTAKE_UNKNOWN_SEX if sex is None else MIN_INTAKE_KCAL[sex]


def _formula(trend_kg: float | None, settings: Settings, today: Date) -> float | None:
    if (
        trend_kg is None
        or settings.sex is None
        or settings.height_cm is None
        or settings.birth_date is None
        or settings.activity is None
    ):
        return None
    ree = calc.mifflin_st_jeor_ree(
        settings.sex,
        trend_kg,
        settings.height_cm,
        calc.age_on(settings.birth_date, today),
    )
    return calc.formula_tdee(ree, settings.activity)


def _missing_body_stats(settings: Settings) -> tuple[str, ...]:
    stats = {
        "sex": settings.sex,
        "height": settings.height_cm,
        "birth date": settings.birth_date,
        "activity level": settings.activity,
    }
    return tuple(name for name, value in stats.items() if value is None)


def _safe_rate(tdee: float, floor: int, settings: Settings) -> float:
    """Fastest loss whose target stays at the floor, truncated in the user's unit."""
    kg_per_week = (floor - tdee) * 7 / settings.energy_density
    shown = weight_from_kg(kg_per_week, settings.weight_unit)
    # Toward zero, so rounding can never push the suggestion under the floor. Six
    # places first, so -49.9999999 hundredths counts as -50, not -49.
    truncated = trunc(round(shown * 100, 6)) / 100
    return weight_to_kg(truncated, settings.weight_unit)


def target_status(estimate: TdeeEstimate | None, settings: Settings) -> TargetStatus:
    if estimate is None:
        return NoTarget()
    tdee = estimate.tdee
    floor = intake_floor(settings.sex)
    if tdee <= 0:
        return EstimateInvalid(tdee)
    if tdee < floor:
        return EstimateLow(tdee, floor)
    rate = settings.rate_kg_per_week
    if rate is None:
        return NoTarget()
    target = calc.daily_target(tdee, rate, settings.energy_density)
    if target >= floor:
        return Target(target)
    safe_rate = _safe_rate(tdee, floor, settings)
    if safe_rate == 0:
        return EstimateLow(tdee, floor)
    return TargetBelowFloor(target, floor, safe_rate)


def goal_status(
    trend_kg: float | None, target: TargetStatus, settings: Settings, today: Date
) -> GoalStatus:
    goal = settings.goal_weight_kg
    if goal is None:
        return NoGoal()
    if trend_kg is None:
        return GoalNoWeight(goal)
    # A zero rate only tests the goal tolerance, so this can't build a far-off date.
    if calc.goal_eta(trend_kg, goal, 0, today) is not None:
        return GoalReached(goal)
    remaining = goal - trend_kg
    rate = settings.rate_kg_per_week
    if not rate:
        return GoalNoRate(goal, remaining)
    if remaining * rate < 0:
        return GoalAway(goal, remaining)
    if isinstance(target, EstimateInvalid | EstimateLow | TargetBelowFloor):
        return GoalNoSafeTarget(goal, remaining)
    # Checked before goal_eta builds a date: tiny rates overflow datetime.date.
    if remaining / rate > MAX_ETA_WEEKS:
        return GoalTooSlow(goal, remaining)
    eta = calc.goal_eta(trend_kg, goal, rate, today)
    assert eta is not None  # direction and rate were checked above
    return GoalOnTrack(goal, eta)


def build_dashboard(logs: list[DayLog], settings: Settings, today: Date) -> Dashboard:
    window = settings.tdee_window_days
    min_span, blend_start, blend_full = calc_params(window)
    trend = tuple(calc.trend(logs))
    trend_kg = trend[-1].trend_kg if trend else None
    progress = calc.window_progress(logs, today, window_days=window)
    logged = calc.logged_tdee(
        logs,
        today,
        window_days=window,
        energy_density=settings.energy_density,
        min_span_days=min_span,
    )
    formula = _formula(trend_kg, settings, today)
    estimate = calc.estimate_tdee(
        logged, formula, blend_start_days=blend_start, blend_full_days=blend_full
    )
    rate = None
    if progress.weigh_ins >= MIN_WEIGH_INS and progress.span_days >= min_span:
        lower = today - timedelta(days=window)
        slope = calc.weight_slope(log for log in logs if lower <= log.date <= today)
        rate = None if slope is None else slope * 7
    target = target_status(estimate, settings)
    return Dashboard(
        today=today,
        has_entries=bool(logs),
        trend=trend,
        rate_kg_per_week=rate,
        estimate=estimate,
        progress=progress,
        weigh_ins_needed=MIN_WEIGH_INS,
        span_needed=min_span,
        full_logs_days=blend_full,
        formula_tdee=formula,
        missing_body_stats=_missing_body_stats(settings),
        target=target,
        goal=goal_status(trend_kg, target, settings, today),
    )


def parse_range(text: str | None) -> Range:
    for option in RANGES:
        if text == option:
            return option
    return DEFAULT_RANGE


@dataclass(frozen=True)
class Chart:
    range: Range
    range_days: int
    start: Date
    end: Date
    points: tuple[TrendPoint, ...]  # weigh-ins in range, with their trend values
    goal_kg: float | None
    projection: tuple[tuple[Date, float], ...]  # (date, kg); empty or two points
    has_weigh_ins: bool  # any at all, for the empty-range message
    # The first weigh-in in range (not the range start) through the end, each with a
    # little room so the outermost dots aren't cut off by the frame.
    axis_start: Date
    axis_end: Date

    @property
    def empty(self) -> bool:
        return not self.points

    @property
    def shorter_than_range(self) -> bool:
        """Data starts well after the range does, so the caption says 'since'."""
        return bool(self.points) and self.points[0].date > self.start + timedelta(7)


@dataclass(frozen=True)
class TableRow:
    date: Date
    weight_kg: float | None
    calories: int | None
    trend_kg: float | None


def build_table(
    logs: list[DayLog], dashboard: Dashboard, chart: Chart
) -> tuple[TableRow, ...]:
    trends = {point.date: point.trend_kg for point in dashboard.trend}
    return tuple(
        TableRow(log.date, log.weight_kg, log.calories, trends.get(log.date))
        for log in sorted(logs, key=lambda log: log.date, reverse=True)
        if chart.start <= log.date <= dashboard.today
    )


def range_days(rng: Range, dashboard: Dashboard) -> int:
    if rng != "all":
        return RANGE_DAYS[rng]
    if not dashboard.trend:
        return MIN_RANGE_DAYS
    return max(MIN_RANGE_DAYS, (dashboard.today - dashboard.trend[0].date).days)


def _projection(
    dashboard: Dashboard, settings: Settings, cap_days: int
) -> tuple[tuple[Date, float], ...]:
    goal, trend_kg, rate = dashboard.goal, dashboard.trend_kg, settings.rate_kg_per_week
    if not isinstance(goal, GoalOnTrack) or trend_kg is None or rate is None:
        return ()
    today = dashboard.today
    if goal.eta.date <= today:
        return ()  # under half a day to go: a zero-length line is noise
    cap_date = today + timedelta(days=cap_days)
    if goal.eta.date <= cap_date:
        # End on the goal itself: a whole day at the rate can overshoot it.
        return ((today, trend_kg), (goal.eta.date, goal.goal_kg))
    end_kg = trend_kg + rate * cap_days / 7
    # The cap comes before the crossing, so this only guards against float error.
    end_kg = max(end_kg, goal.goal_kg) if rate < 0 else min(end_kg, goal.goal_kg)
    return ((today, trend_kg), (cap_date, end_kg))


def build_chart(dashboard: Dashboard, settings: Settings, rng: Range) -> Chart:
    days = range_days(rng, dashboard)
    start = dashboard.today - timedelta(days=days)
    projection = _projection(dashboard, settings, days // 4)
    end = projection[-1][0] if projection else dashboard.today
    points = tuple(point for point in dashboard.trend if point.date >= start)
    first = points[0].date if points else start
    # Start at the data, not the range, but never narrower than a week.
    data_start = min(first, end - timedelta(days=MIN_AXIS_DAYS))
    padding = timedelta(days=max(1, (end - data_start).days // 50))
    return Chart(
        range=rng,
        range_days=days,
        start=start,
        end=end,
        points=points,
        goal_kg=settings.goal_weight_kg,
        projection=projection,
        has_weigh_ins=bool(dashboard.trend),
        axis_start=data_start - padding,
        axis_end=end + padding,
    )


def chart_payload(chart: Chart, unit: WeightUnit) -> dict[str, object]:
    """JSON for dashboard.js, in display units rounded as the tables show them."""

    def shown(kg: float) -> float:
        return round(weight_from_kg(kg, unit), 1)

    return {
        "unit": unit.value,
        "start": chart.axis_start.isoformat(),
        "end": chart.axis_end.isoformat(),
        "weighIns": [
            {"x": point.date.isoformat(), "y": shown(point.weight_kg)}
            for point in chart.points
        ],
        "trend": [
            {"x": point.date.isoformat(), "y": shown(point.trend_kg)}
            for point in chart.points
        ],
        "goal": None if chart.goal_kg is None else shown(chart.goal_kg),
        "projection": [
            {"x": day.isoformat(), "y": shown(kg)} for day, kg in chart.projection
        ],
    }
