from datetime import date as Date

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from tdee_calculator import clock, measurements
from tdee_calculator.body_fat import build_summary
from tdee_calculator.calc import Site
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
    summary = build_summary(measurements.all_sessions(session), settings)
    unit = length_unit_for(settings.weight_unit)
    return templates.TemplateResponse(
        request=request,
        name="measurements.html",
        context={
            "settings": settings,
            "today": clock.today(),
            "form_values": values,
            "errors": errors or {},
            "rows": summary.rows,
            "latest": summary.latest,
            "newer": summary.newer,
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
