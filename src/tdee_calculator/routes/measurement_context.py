"""Shared measurement form context and links for its two pages."""

from dataclasses import dataclass
from datetime import date as Date
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from tdee_calculator import measurements
from tdee_calculator.calc import Site
from tdee_calculator.dashboard import Range
from tdee_calculator.edits import row_version
from tdee_calculator.measurement_form import READING_LIMITS, SITE_LABELS
from tdee_calculator.settings import Settings
from tdee_calculator.units import format_length, length_unit_for


def measurement_values(
    session: Session, day: Date, settings: Settings
) -> dict[str, str]:
    row = measurements.get_session(session, day)
    values = {f"{site.value}_{slot}": "" for site in Site for slot in range(1, 4)}
    values.update(
        date=day.isoformat(),
        loaded_date=day.isoformat(),
        loaded_version=row_version(row),
        weight_unit=settings.weight_unit.value,
    )
    if row is not None:
        for reading in row.readings:
            values[f"{reading.site}_{reading.reading}"] = format_length(
                reading.value_cm, length_unit_for(settings.weight_unit)
            )
    return values


def measurement_url(
    day: Date,
    *,
    home_date: Date | None = None,
    chart_range: Range = "3m",
    saved: bool = False,
) -> str:
    if home_date is None:
        params = {"date": day.isoformat()}
        if saved:
            params["saved"] = day.isoformat()
        return "/measurements?" + urlencode(params)
    params = {
        "date": home_date.isoformat(),
        "range": chart_range,
        "circumference_date": day.isoformat(),
    }
    if saved:
        params["circumference_saved"] = day.isoformat()
    return "/?" + urlencode(params)


@dataclass(frozen=True)
class MeasurementFormContext:
    values: dict[str, str]
    errors: dict[str, str]
    sites: dict[Site, str]
    length_unit: str
    limits: dict[Site, tuple[str, str]]
    saved: Date | None
    notice: str | None
    conflict_date: Date | None
    stale_date: Date | None
    edit_url: str | None
    reload_url: str | None
    home_date: Date | None
    chart_range: Range


def build_form_context(
    settings: Settings,
    values: dict[str, str],
    *,
    errors: dict[str, str] | None = None,
    saved: Date | None = None,
    notice: str | None = None,
    conflict_date: Date | None = None,
    stale_date: Date | None = None,
    home_date: Date | None = None,
    chart_range: Range = "3m",
) -> MeasurementFormContext:
    unit = length_unit_for(settings.weight_unit)
    return MeasurementFormContext(
        values=values,
        errors=errors or {},
        sites=SITE_LABELS,
        length_unit=unit.value,
        limits={
            site: (format_length(lower, unit), format_length(upper, unit))
            for site, (lower, upper) in READING_LIMITS.items()
        },
        saved=saved,
        notice=notice,
        conflict_date=conflict_date,
        stale_date=stale_date,
        edit_url=measurement_url(
            conflict_date, home_date=home_date, chart_range=chart_range
        )
        if conflict_date is not None
        else None,
        reload_url=measurement_url(
            stale_date, home_date=home_date, chart_range=chart_range
        )
        if stale_date is not None
        else None,
        home_date=home_date,
        chart_range=chart_range,
    )
