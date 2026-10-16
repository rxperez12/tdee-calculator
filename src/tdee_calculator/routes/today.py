from datetime import date as Date

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from tdee_calculator import entries, measurements
from tdee_calculator.body_fat import build_row
from tdee_calculator.dashboard import (
    RANGE_LABELS,
    RANGES,
    build_chart,
    build_dashboard,
    build_table,
    chart_payload,
)
from tdee_calculator.edits import edit_conflict, row_version
from tdee_calculator.entry_form import (
    MAX_CALORIES,
    MIN_CALORIES,
    EntryFormErrors,
    parse_entry_form,
)
from tdee_calculator.logging_calendar import build_calendar
from tdee_calculator.measurement_dashboard import build_measurement_dashboard
from tdee_calculator.routes.calendar_context import Workspace, WorkspaceDependency
from tdee_calculator.routes.measurement_context import (
    MeasurementFormContext,
    build_form_context,
    measurement_values,
)
from tdee_calculator.settings import Settings
from tdee_calculator.units import (
    MAX_WEIGHT_KG,
    MIN_WEIGHT_KG,
    format_energy,
    format_weight,
)
from tdee_calculator.web import (
    STALE_UNITS_NOTICE,
    FormDependency,
    SessionDependency,
    SettingsDependency,
    templates,
    units_match,
)

router = APIRouter()
ENTRY_FIELDS = (
    "entry_date",
    "loaded_date",
    "loaded_version",
    "weight",
    "calories",
    "weight_unit",
    "energy_unit",
)


def entry_values(
    session: Session, form_date: Date, settings: Settings
) -> dict[str, str]:
    entry = entries.get_entry(session, form_date)
    return {
        "entry_date": form_date.isoformat(),
        "loaded_date": form_date.isoformat(),
        "loaded_version": row_version(entry),
        "weight_unit": settings.weight_unit.value,
        "energy_unit": settings.energy_unit.value,
        "weight": format_weight(entry.weight_kg, settings.weight_unit)
        if entry is not None and entry.weight_kg is not None
        else "",
        "calories": format_energy(entry.calories, settings.energy_unit)
        if entry is not None and entry.calories is not None
        else "",
    }


def render_home(
    request: Request,
    session: Session,
    form_values: dict[str, str],
    settings: Settings,
    errors: dict[str, str] | None = None,
    status_code: int = 200,
    saved: Date | None = None,
    conflict_date: Date | None = None,
    stale_date: Date | None = None,
    notice: str | None = None,
    measurement_form: MeasurementFormContext | None = None,
    circumference_saved: Date | None = None,
    *,
    workspace: Workspace,
) -> HTMLResponse:
    today = workspace.today
    try:
        form_date = Date.fromisoformat(form_values["entry_date"])
    except ValueError:
        form_date = None
    logs = entries.all_day_logs(session)
    sessions = measurements.all_sessions(session)
    chart_range = workspace.chart_range
    dashboard = build_dashboard(logs, settings, today)
    chart = build_chart(dashboard, settings, chart_range)
    circumference_open = workspace.measurements_open or measurement_form is not None
    home_date = workspace.day
    if measurement_form is None:
        measurement_form = build_form_context(
            settings,
            measurement_values(session, home_date, settings),
            saved=circumference_saved,
            workspace=workspace,
        )
    measurement_dashboard = build_measurement_dashboard(sessions, settings, today)
    calendar = build_calendar(
        logs,
        [build_row(row, settings) for row in sessions],
        settings,
        today,
        workspace.month,
        workspace.day,
        workspace.stats,
    )
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "form_values": form_values,
            "form_date": form_date,
            "errors": errors or {},
            "today": today,
            "dashboard": dashboard,
            "chart": chart,
            "table_rows": build_table(logs, dashboard, chart),
            "chart_data": chart_payload(chart, settings.weight_unit),
            "ranges": RANGES,
            "range_labels": RANGE_LABELS,
            "saved": saved,
            "conflict_date": conflict_date,
            "stale_date": stale_date,
            "settings": settings,
            "notice": notice,
            "weight_min": format_weight(MIN_WEIGHT_KG, settings.weight_unit),
            "weight_max": format_weight(MAX_WEIGHT_KG, settings.weight_unit),
            "energy_min": format_energy(MIN_CALORIES, settings.energy_unit),
            "energy_max": format_energy(MAX_CALORIES, settings.energy_unit),
            "measurement_dashboard": measurement_dashboard,
            "measurement_form": measurement_form,
            "circumference_open": circumference_open,
            "workspace": workspace,
            "calendar": calendar,
            "circumference_log_url": workspace.url(day=today, measurements_open=True),
            "circumference_edit_url": workspace.url(
                day=measurement_dashboard.newest.date, measurements_open=True
            )
            if measurement_dashboard.newest is not None
            else None,
        },
        status_code=status_code,
    )


@router.get("/")
def home(
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    workspace: WorkspaceDependency,
    saved: Date | None = None,
    circumference_saved: Date | None = None,
) -> HTMLResponse:
    values = entry_values(session, workspace.day, settings)
    return render_home(
        request,
        session,
        values,
        settings,
        saved=saved,
        circumference_saved=circumference_saved,
        workspace=workspace,
    )


@router.post("/entries", response_model=None)
def save_entry(
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    form: FormDependency,
    workspace: WorkspaceDependency,
) -> HTMLResponse | RedirectResponse:
    values = {key: form.get(key, "") for key in ENTRY_FIELDS}
    try:
        parsed_date = Date.fromisoformat(values["entry_date"].strip())
    except ValueError:
        parsed_date = None
    if not units_match(values, settings):
        fresh = entry_values(session, workspace.day, settings)
        return render_home(
            request,
            session,
            fresh,
            settings,
            status_code=409,
            notice=STALE_UNITS_NOTICE,
            workspace=workspace,
        )
    current = (
        entries.get_entry(session, parsed_date) if parsed_date is not None else None
    )
    result = parse_entry_form(
        values["entry_date"],
        values["weight"],
        values["calories"],
        workspace.today,
        settings.weight_unit,
        settings.energy_unit,
        current,
    )
    if isinstance(result, EntryFormErrors):
        return render_home(
            request,
            session,
            values,
            settings,
            result.errors,
            status_code=422,
            workspace=workspace,
        )
    # The form replaces both fields, so saving it is only safe if the row is
    # still what the form showed, not something another tab saved since.
    conflict = edit_conflict(
        result.date, values["loaded_date"], values["loaded_version"], current
    )
    saved = None
    if conflict is None:
        saved = entries.upsert_entry_if_unchanged(session, result, row_version(current))
    if conflict is None and saved is None:
        # Another save landed after the check: explain it as if it came first.
        latest = entries.get_entry(session, result.date)
        conflict = edit_conflict(
            result.date, values["loaded_date"], values["loaded_version"], latest
        )
        conflict = conflict or "stale"
    if conflict is not None:
        return render_home(
            request,
            session,
            values,
            settings,
            status_code=409,
            conflict_date=result.date if conflict == "conflict" else None,
            stale_date=result.date if conflict == "stale" else None,
            workspace=workspace,
        )
    return RedirectResponse(
        workspace.for_day(result.date).url(saved=True),
        status_code=303,
    )


@router.post("/entries/{entry_date}/delete")
def remove_entry(entry_date: Date, session: SessionDependency) -> RedirectResponse:
    entries.delete_entry(session, entry_date)
    return RedirectResponse("/history", status_code=303)
