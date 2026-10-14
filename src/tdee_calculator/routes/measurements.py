from datetime import date as Date

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from tdee_calculator import clock, measurements
from tdee_calculator.body_fat import build_summary
from tdee_calculator.calc import navy_measurement_sites
from tdee_calculator.dashboard import parse_range
from tdee_calculator.edits import edit_conflict, row_version
from tdee_calculator.measurement_form import (
    MeasurementFormErrors,
    parse_measurement_form,
)
from tdee_calculator.routes.measurement_context import (
    build_form_context,
    measurement_url,
    measurement_values,
)
from tdee_calculator.routes.today import entry_values, render_home
from tdee_calculator.settings import Settings
from tdee_calculator.web import (
    STALE_UNITS_NOTICE,
    FormDependency,
    SessionDependency,
    SettingsDependency,
    requested_day,
    templates,
    weight_unit_matches,
)

router = APIRouter()


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
    return templates.TemplateResponse(
        request=request,
        name="measurements.html",
        context={
            "settings": settings,
            "today": clock.today(),
            "rows": summary.rows,
            "latest": summary.latest,
            "newer": summary.newer,
            "measurement_form": build_form_context(
                settings,
                values,
                errors=errors,
                saved=saved,
                conflict_date=conflict_date,
                stale_date=stale_date,
                notice=notice,
            ),
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
    day = requested_day(date, clock.today())
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
    home_date = (
        requested_day(values.get("home_date"), clock.today())
        if values.get("source") == "home"
        else None
    )
    chart_range = parse_range(values.get("range"))

    def render_failure(
        form_values: dict[str, str],
        *,
        status_code: int,
        errors: dict[str, str] | None = None,
        conflict_date: Date | None = None,
        stale_date: Date | None = None,
        notice: str | None = None,
    ) -> HTMLResponse:
        if home_date is None:
            return render_measurements(
                request,
                session,
                settings,
                form_values,
                status_code=status_code,
                errors=errors,
                conflict_date=conflict_date,
                stale_date=stale_date,
                notice=notice,
            )
        return render_home(
            request,
            session,
            entry_values(session, home_date, settings),
            settings,
            status_code=status_code,
            chart_range=chart_range,
            measurement_form=build_form_context(
                settings,
                form_values,
                errors=errors,
                conflict_date=conflict_date,
                stale_date=stale_date,
                notice=notice,
                home_date=home_date,
                chart_range=chart_range,
            ),
        )

    try:
        day = Date.fromisoformat(values.get("date", "").strip())
    except ValueError:
        day = None
    if not weight_unit_matches(values, settings):
        return render_failure(
            measurement_values(session, day or clock.today(), settings),
            status_code=409,
            notice=STALE_UNITS_NOTICE,
        )
    if settings.sex is None:
        return render_failure(
            values,
            status_code=422,
            errors={
                "form": "Choose male or female in Settings before logging measurements."
            },
        )
    if values.get("sex") != settings.sex.value:
        return render_failure(
            measurement_values(session, day or clock.today(), settings),
            status_code=409,
            notice=(
                "Your sex setting changed since this page loaded. Nothing was saved. "
                "Check the displayed measurements and submit again."
            ),
        )
    current = measurements.get_session(session, day) if day is not None else None
    result = parse_measurement_form(
        values,
        clock.today(),
        settings.weight_unit,
        current,
        sites=navy_measurement_sites(settings.sex),
    )
    if isinstance(result, MeasurementFormErrors):
        return render_failure(values, errors=result.errors, status_code=422)
    loaded_date = values.get("loaded_date", "")
    loaded_version = values.get("loaded_version", "")
    conflict = edit_conflict(result.date, loaded_date, loaded_version, current)
    saved = None
    if conflict is None:
        saved = measurements.upsert_session_if_unchanged(
            session, result, row_version(current)
        )
    if conflict is None and saved is None:
        # Another save landed after the check: explain it as if it came first.
        latest = measurements.get_session(session, result.date)
        conflict = edit_conflict(result.date, loaded_date, loaded_version, latest)
        conflict = conflict or "stale"
    if conflict is not None:
        return render_failure(
            values,
            status_code=409,
            conflict_date=result.date if conflict == "conflict" else None,
            stale_date=result.date if conflict == "stale" else None,
        )
    return RedirectResponse(
        measurement_url(
            result.date, home_date=home_date, chart_range=chart_range, saved=True
        ),
        status_code=303,
    )


@router.post("/measurements/{date}/delete")
def remove(date: Date, session: SessionDependency) -> RedirectResponse:
    measurements.delete_session(session, date)
    return RedirectResponse("/measurements", status_code=303)
