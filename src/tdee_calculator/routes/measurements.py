from dataclasses import dataclass
from datetime import date as Date

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from tdee_calculator import clock, measurements
from tdee_calculator.calc import Sex, Site, mean_reading, navy_body_fat
from tdee_calculator.measurement_form import (
    READING_LIMITS,
    SITE_LABELS,
    MeasurementFormErrors,
    parse_measurement_form,
)
from tdee_calculator.models import MeasurementSession
from tdee_calculator.settings import Settings
from tdee_calculator.units import format_length, length_unit_for
from tdee_calculator.web import (
    STALE_UNITS_NOTICE,
    FormDependency,
    SessionDependency,
    SettingsDependency,
    templates,
    weight_unit_matches,
)

router = APIRouter()


@dataclass(frozen=True)
class MeasurementRow:
    date: Date
    means: dict[Site, str]
    estimate: float | None
    reason: str
    needs_settings: bool = False


def measurement_version(row: MeasurementSession | None) -> str:
    return "" if row is None else row.updated_at.isoformat()


def measurement_values(
    session: Session, day: Date, settings: Settings
) -> dict[str, str]:
    row = measurements.get_session(session, day)
    values = {f"{site.value}_{slot}": "" for site in Site for slot in range(1, 4)}
    values.update(
        date=day.isoformat(),
        loaded_date=day.isoformat(),
        loaded_version=measurement_version(row),
        weight_unit=settings.weight_unit.value,
    )
    if row is not None:
        for reading in row.readings:
            values[f"{reading.site}_{reading.reading}"] = format_length(
                reading.value_cm, length_unit_for(settings.weight_unit)
            )
    return values


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
    if estimate is None or not 2 <= estimate <= 60:
        return MeasurementRow(row.date, formatted, None, "Outside the equation's range")
    return MeasurementRow(row.date, formatted, estimate, "")


def render_measurements(
    request: Request,
    session: Session,
    settings: Settings,
    values: dict[str, str],
    *,
    errors: dict[str, str] | None = None,
    status_code: int = 200,
    saved: Date | None = None,
    conflict_date: Date | None = None,
    stale_date: Date | None = None,
    notice: str | None = None,
) -> HTMLResponse:
    rows = [build_row(row, settings) for row in measurements.all_sessions(session)]
    latest = next((row for row in rows if row.estimate is not None), None)
    newer = [row for row in rows if latest is not None and row.date > latest.date]
    unit = length_unit_for(settings.weight_unit)
    return templates.TemplateResponse(
        request=request,
        name="measurements.html",
        context={
            "settings": settings,
            "today": clock.today(),
            "form_values": values,
            "errors": errors or {},
            "rows": rows,
            "latest": latest,
            "newer": newer,
            "sites": SITE_LABELS,
            "length_unit": unit.value,
            "limits": {
                site: (format_length(lower, unit), format_length(upper, unit))
                for site, (lower, upper) in READING_LIMITS.items()
            },
            "saved": saved,
            "conflict_date": conflict_date,
            "stale_date": stale_date,
            "notice": notice,
        },
        status_code=status_code,
    )


@router.get("/measurements")
def page(
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    date: str | None = None,
    saved: Date | None = None,
) -> HTMLResponse:
    today = clock.today()
    try:
        day = Date.fromisoformat(date or "")
    except ValueError:
        day = today
    if day > today:
        day = today
    return render_measurements(
        request,
        session,
        settings,
        measurement_values(session, day, settings),
        saved=saved,
    )


@router.post("/measurements", response_model=None)
def save(
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    values: FormDependency,
) -> HTMLResponse | RedirectResponse:
    try:
        day = Date.fromisoformat(values.get("date", "").strip())
    except ValueError:
        day = None
    if not weight_unit_matches(values, settings):
        return render_measurements(
            request,
            session,
            settings,
            measurement_values(session, day or clock.today(), settings),
            status_code=409,
            notice=STALE_UNITS_NOTICE,
        )
    current = measurements.get_session(session, day) if day is not None else None
    result = parse_measurement_form(
        values, clock.today(), settings.weight_unit, current
    )
    if isinstance(result, MeasurementFormErrors):
        return render_measurements(
            request, session, settings, values, errors=result.errors, status_code=422
        )
    try:
        loaded = Date.fromisoformat(values.get("loaded_date", ""))
    except ValueError:
        loaded = None
    if result.date != loaded and current is not None:
        return render_measurements(
            request,
            session,
            settings,
            values,
            status_code=409,
            conflict_date=result.date,
        )
    if result.date == loaded and values.get(
        "loaded_version", ""
    ) != measurement_version(current):
        return render_measurements(
            request, session, settings, values, status_code=409, stale_date=result.date
        )
    measurements.upsert_session(session, result)
    saved_date = result.date.isoformat()
    return RedirectResponse(
        f"/measurements?date={saved_date}&saved={saved_date}", status_code=303
    )


@router.post("/measurements/{date}/delete")
def remove(date: Date, session: SessionDependency) -> RedirectResponse:
    measurements.delete_session(session, date)
    return RedirectResponse("/measurements", status_code=303)
