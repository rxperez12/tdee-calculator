"""Shared measurement form context and links for its two pages."""

from dataclasses import dataclass
from datetime import date as Date
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from tdee_calculator import measurements
from tdee_calculator.calc import Site, navy_measurement_sites
from tdee_calculator.edits import row_version
from tdee_calculator.measurement_form import READING_LIMITS, SITE_LABELS
from tdee_calculator.routes.calendar_context import Workspace
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
        sex=settings.sex.value if settings.sex is not None else "",
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
    saved: bool = False,
) -> str:
    params = {"date": day.isoformat()}
    if saved:
        params["saved"] = day.isoformat()
    return "/measurements?" + urlencode(params)


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
    workspace: Workspace | None


def build_form_context(
    settings: Settings,
    values: dict[str, str],
    *,
    errors: dict[str, str] | None = None,
    saved: Date | None = None,
    notice: str | None = None,
    conflict_date: Date | None = None,
    stale_date: Date | None = None,
    workspace: Workspace | None = None,
) -> MeasurementFormContext:
    unit = length_unit_for(settings.weight_unit)
    return MeasurementFormContext(
        values=values,
        errors=errors or {},
        sites={site: SITE_LABELS[site] for site in navy_measurement_sites(settings.sex)}
        if settings.sex is not None
        else {},
        length_unit=unit.value,
        limits={
            site: (format_length(lower, unit), format_length(upper, unit))
            for site, (lower, upper) in READING_LIMITS.items()
        },
        saved=saved,
        notice=notice,
        conflict_date=conflict_date,
        stale_date=stale_date,
        edit_url=workspace.url(
            day=conflict_date, month=workspace.month, measurements_open=True
        )
        if workspace is not None and conflict_date is not None
        else measurement_url(conflict_date)
        if conflict_date is not None
        else None,
        reload_url=workspace.url(
            day=stale_date, month=workspace.month, measurements_open=True
        )
        if workspace is not None and stale_date is not None
        else measurement_url(stale_date)
        if stale_date is not None
        else None,
        workspace=workspace,
    )
