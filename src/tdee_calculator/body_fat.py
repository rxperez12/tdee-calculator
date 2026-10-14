"""The Measurements page's view model: Navy estimates and why one is missing.

Pure, like dashboard.py: no database, clock, or web imports. Sessions are passed in
newest first; site means are formatted in the length unit that follows the weight unit.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date as Date

from tdee_calculator.calc import Sex, Site, mean_reading, navy_body_fat
from tdee_calculator.models import MeasurementSession
from tdee_calculator.settings import Settings
from tdee_calculator.units import format_length, length_unit_for

# Sanity bounds beyond the equation's own domain: typos that pass the per-site
# range check can still produce an absurd percentage.
MIN_ESTIMATE = 2
MAX_ESTIMATE = 60


@dataclass(frozen=True)
class MeasurementRow:
    date: Date
    means: dict[Site, str]
    estimate: float | None
    reason: str
    needs_settings: bool = False


@dataclass(frozen=True)
class MeasurementSummary:
    rows: tuple[MeasurementRow, ...]  # newest first
    latest: MeasurementRow | None  # newest row with an estimate
    newer: tuple[MeasurementRow, ...]  # rows after `latest` that have none


def build_row(row: MeasurementSession, settings: Settings) -> MeasurementRow:
    means = {
        site: mean_reading(values)
        for site in Site
        if (values := [r.value_cm for r in row.readings if r.site == site.value])
    }
    formatted = {
        site: format_length(value, length_unit_for(settings.weight_unit))
        for site, value in means.items()
    }
    missing_settings = []
    if settings.sex is None:
        missing_settings.append("sex")
    if settings.height_cm is None:
        missing_settings.append("height")
    if missing_settings:
        return MeasurementRow(
            row.date,
            formatted,
            None,
            f"Set {' and '.join(missing_settings)} in Settings",
            needs_settings=True,
        )
    assert settings.sex is not None
    assert settings.height_cm is not None
    required = (
        (Site.NECK, Site.ABDOMEN)
        if settings.sex == Sex.MALE
        else (Site.NECK, Site.WAIST, Site.HIP)
    )
    missing = [site.value for site in required if site not in means]
    if missing:
        return MeasurementRow(
            row.date, formatted, None, f"Needs {' and '.join(missing)}"
        )
    try:
        estimate = navy_body_fat(settings.sex, settings.height_cm, means)
    except ValueError:
        estimate = None
    if estimate is None or not MIN_ESTIMATE <= estimate <= MAX_ESTIMATE:
        return MeasurementRow(row.date, formatted, None, "Outside the equation's range")
    return MeasurementRow(row.date, formatted, estimate, "")


def build_summary(
    sessions: Sequence[MeasurementSession], settings: Settings
) -> MeasurementSummary:
    rows = tuple(build_row(row, settings) for row in sessions)
    latest = next((row for row in rows if row.estimate is not None), None)
    newer = tuple(row for row in rows if latest is not None and row.date > latest.date)
    return MeasurementSummary(rows, latest, newer)
