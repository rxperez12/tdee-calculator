"""Pure calendar presentation and logging streaks, with dates passed in."""

from calendar import Calendar
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date as Date
from datetime import timedelta
from typing import Literal

from tdee_calculator.body_fat import MeasurementRow
from tdee_calculator.calc import DayLog, Site, navy_measurement_sites
from tdee_calculator.measurement_form import SITE_LABELS
from tdee_calculator.settings import Settings
from tdee_calculator.units import format_energy, format_weight, length_unit_for

Presence = Literal[
    "before", "weight", "calories", "both", "missing", "progress", "future"
]
STATUS_LABELS: dict[Presence, str] = {
    "before": "Before tracking",
    "weight": "Weight only",
    "calories": "Calories only",
    "both": "Both logged",
    "missing": "No logs",
    "progress": "In progress",
    "future": "Future",
}


@dataclass(frozen=True)
class StatOption:
    key: str
    label: str
    unit: str
    estimated: bool = False


@dataclass(frozen=True)
class StatValue:
    key: str
    label: str
    unit: str
    value: str | None
    estimated: bool
    reason: str = "Not recorded"


@dataclass(frozen=True)
class Streak:
    count: int
    through: Date | None


@dataclass(frozen=True)
class CalendarDay:
    date: Date
    status: Presence
    has_weight: bool
    has_calories: bool
    has_measurements: bool
    values: tuple[StatValue, ...]

    @property
    def label(self) -> str:
        return STATUS_LABELS[self.status]

    @property
    def missing(self) -> str:
        return (
            "weight and calories"
            if not self.has_weight and not self.has_calories
            else "calories"
            if self.has_weight
            else "weight"
        )


@dataclass(frozen=True)
class LoggingCalendar:
    month: Date
    previous: Date | None
    next: Date | None
    weeks: tuple[tuple[CalendarDay | None, ...], ...]
    selected: CalendarDay
    incomplete: tuple[CalendarDay, ...]
    tracking_start: Date | None
    options: tuple[StatOption, ...]
    selected_stats: tuple[str, ...]
    weight_streak: Streak
    calorie_streak: Streak


def stat_options(settings: Settings) -> tuple[StatOption, ...]:
    sites = navy_measurement_sites(settings.sex) if settings.sex is not None else ()
    return (
        StatOption("weight", "Weight", settings.weight_unit.value),
        StatOption("calories", "Calories", settings.energy_unit.value),
        *(
            StatOption(
                site.value,
                SITE_LABELS[site],
                length_unit_for(settings.weight_unit).value,
            )
            for site in sites
        ),
        StatOption("navy", "Body fat · Navy estimate", "%", estimated=True),
    )


def current_streak(days: set[Date], today: Date) -> Streak:
    anchor = (
        today
        if today in days
        else today - timedelta(days=1)
        if today > Date.min
        else today
    )
    if anchor not in days:
        return Streak(0, None)
    day, count = anchor, 0
    while day in days:
        count += 1
        if day == Date.min:
            break
        day -= timedelta(days=1)
    return Streak(count, anchor)


def build_calendar(
    logs: Sequence[DayLog],
    measurements: Sequence[MeasurementRow],
    settings: Settings,
    today: Date,
    month: Date,
    selected: Date,
    stats: tuple[str, ...] | None = None,
) -> LoggingCalendar:
    options = stat_options(settings)
    selected_stats = tuple(
        option.key
        for option in options
        if option.key in (stats if stats is not None else ("weight", "calories"))
    )
    by_date = {log.date: log for log in logs}
    sessions = {row.date: row for row in measurements}
    weights = {log.date for log in logs if log.weight_kg is not None}
    calories = {log.date for log in logs if log.calories is not None}
    tracking_start = min(weights | calories, default=None)

    def cell(day: Date) -> CalendarDay:
        weight, energy = day in weights, day in calories
        status: Presence
        if day > today:
            status = "future"
        elif weight and energy:
            status = "both"
        elif day == today:
            status = "progress"
        elif tracking_start is None or day < tracking_start:
            status = "before"
        else:
            status = "weight" if weight else "calories" if energy else "missing"
        log, row = by_date.get(day), sessions.get(day)
        values = []
        for option in options:
            if option.key not in selected_stats:
                continue
            value = None
            reason = "Not recorded"
            if option.key == "weight":
                if log is not None and log.weight_kg is not None:
                    value = format_weight(log.weight_kg, settings.weight_unit)
            elif option.key == "calories":
                if log is not None and log.calories is not None:
                    value = format_energy(log.calories, settings.energy_unit)
            elif option.key == "navy":
                if row is not None:
                    value = f"{row.estimate:.0f}" if row.estimate is not None else None
                    reason = row.reason
                else:
                    reason = "No measurements"
            elif row is not None:
                value = row.means.get(Site(option.key))
            values.append(
                StatValue(
                    option.key,
                    option.label,
                    option.unit,
                    value,
                    option.estimated,
                    reason,
                )
            )
        return CalendarDay(day, status, weight, energy, row is not None, tuple(values))

    month = month.replace(day=1)
    weeks = tuple(
        tuple(cell(Date(month.year, month.month, day)) if day else None for day in week)
        for week in Calendar().monthdayscalendar(month.year, month.month)
    )
    previous = (month - timedelta(days=1)).replace(day=1) if month > Date.min else None
    following = (
        Date(month.year + (month.month == 12), month.month % 12 + 1, 1)
        if (month.year, month.month) < (9999, 12)
        else None
    )
    incomplete = tuple(
        day
        for week in weeks
        for day in week
        if day is not None
        and day.date < today
        and day.status in ("weight", "calories", "missing")
    )
    return LoggingCalendar(
        month,
        previous,
        following,
        weeks,
        cell(selected),
        incomplete,
        tracking_start,
        options,
        selected_stats,
        current_streak(weights, today),
        current_streak(calories, today),
    )
