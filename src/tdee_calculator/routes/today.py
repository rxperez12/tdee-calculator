from datetime import date as Date
from typing import Annotated

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from tdee_calculator import clock, entries
from tdee_calculator.dashboard import (
    RANGE_LABELS,
    RANGES,
    Range,
    build_chart,
    build_dashboard,
    chart_payload,
    parse_range,
)
from tdee_calculator.entry_form import (
    MAX_CALORIES,
    MAX_WEIGHT_KG,
    MIN_CALORIES,
    MIN_WEIGHT_KG,
    EntryFormErrors,
    parse_entry_form,
)
from tdee_calculator.models import Entry
from tdee_calculator.settings import Settings
from tdee_calculator.units import format_energy, format_weight
from tdee_calculator.web import (
    STALE_UNITS_NOTICE,
    SessionDependency,
    SettingsDependency,
    templates,
    units_match,
)

router = APIRouter()


def entry_version(entry: Entry | None) -> str:
    return "" if entry is None else entry.updated_at.isoformat()


def entry_values(
    session: Session, form_date: Date, settings: Settings
) -> dict[str, str]:
    entry = entries.get_entry(session, form_date)
    return {
        "entry_date": form_date.isoformat(),
        "loaded_date": form_date.isoformat(),
        "loaded_version": entry_version(entry),
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
    chart_range: Range = "3m",
) -> HTMLResponse:
    today = clock.today()
    try:
        form_date = Date.fromisoformat(form_values["entry_date"])
    except ValueError:
        form_date = None
    is_update = (
        form_date is not None and entries.get_entry(session, form_date) is not None
    )
    dashboard = build_dashboard(entries.all_day_logs(session), settings, today)
    chart = build_chart(dashboard, settings, chart_range)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "form_values": form_values,
            "errors": errors or {},
            "today": today,
            "dashboard": dashboard,
            "chart": chart,
            "chart_data": chart_payload(chart, settings.weight_unit),
            "ranges": RANGES,
            "range_labels": RANGE_LABELS,
            # Range links keep an edit in progress on another day.
            "link_date": form_date.isoformat()
            if form_date is not None and form_date != today
            else None,
            "saved": saved,
            "conflict_date": conflict_date,
            "stale_date": stale_date,
            "is_update": is_update,
            "settings": settings,
            "notice": notice,
            "weight_min": format_weight(MIN_WEIGHT_KG, settings.weight_unit),
            "weight_max": format_weight(MAX_WEIGHT_KG, settings.weight_unit),
            "energy_min": format_energy(MIN_CALORIES, settings.energy_unit),
            "energy_max": format_energy(MAX_CALORIES, settings.energy_unit),
        },
        status_code=status_code,
    )


@router.get("/")
def home(
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    date: Date | None = None,
    saved: Date | None = None,
    chart_range: Annotated[str | None, Query(alias="range")] = None,
) -> HTMLResponse:
    form_date = date or clock.today()
    values = entry_values(session, form_date, settings)
    return render_home(
        request,
        session,
        values,
        settings,
        saved=saved,
        chart_range=parse_range(chart_range),
    )


@router.post("/entries", response_model=None)
def save_entry(
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    entry_date: Annotated[str, Form()] = "",
    loaded_date: Annotated[str, Form()] = "",
    loaded_version: Annotated[str, Form()] = "",
    weight: Annotated[str, Form()] = "",
    calories: Annotated[str, Form()] = "",
    weight_unit: Annotated[str, Form()] = "",
    energy_unit: Annotated[str, Form()] = "",
) -> HTMLResponse | RedirectResponse:
    values = {
        "entry_date": entry_date,
        "loaded_date": loaded_date,
        "loaded_version": loaded_version,
        "weight": weight,
        "calories": calories,
        "weight_unit": weight_unit,
        "energy_unit": energy_unit,
    }
    try:
        parsed_date = Date.fromisoformat(entry_date.strip())
    except ValueError:
        parsed_date = None
    if not units_match(values, settings):
        fresh = entry_values(session, parsed_date or clock.today(), settings)
        return render_home(
            request,
            session,
            fresh,
            settings,
            status_code=409,
            notice=STALE_UNITS_NOTICE,
        )
    current = (
        entries.get_entry(session, parsed_date) if parsed_date is not None else None
    )
    result = parse_entry_form(
        entry_date,
        weight,
        calories,
        clock.today(),
        settings.weight_unit,
        settings.energy_unit,
        current,
    )
    if isinstance(result, EntryFormErrors):
        return render_home(
            request, session, values, settings, result.errors, status_code=422
        )
    loaded: Date | None
    try:
        loaded = Date.fromisoformat(loaded_date)
    except ValueError:
        loaded = None
    if result.date != loaded and current is not None:
        return render_home(
            request,
            session,
            values,
            settings,
            status_code=409,
            conflict_date=result.date,
        )
    # The form replaces both fields, so saving it is only safe if the row is
    # still what the form showed, not something another tab saved since.
    if result.date == loaded and loaded_version != entry_version(current):
        return render_home(
            request,
            session,
            values,
            settings,
            status_code=409,
            stale_date=result.date,
        )
    entries.upsert_entry(session, result)
    return RedirectResponse(f"/?saved={result.date.isoformat()}", status_code=303)


@router.post("/entries/{entry_date}/delete")
def remove_entry(entry_date: Date, session: SessionDependency) -> RedirectResponse:
    entries.delete_entry(session, entry_date)
    return RedirectResponse("/history", status_code=303)
