from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from tdee_calculator import clock
from tdee_calculator.entry_form import MAX_WEIGHT_KG, MIN_WEIGHT_KG
from tdee_calculator.settings import Settings, save_settings
from tdee_calculator.settings_form import (
    ACTIVITY_LABELS,
    MAX_DENSITY,
    MAX_HEIGHT_CM,
    MAX_RATE,
    MAX_WINDOW,
    MIN_DENSITY,
    MIN_HEIGHT_CM,
    MIN_RATE,
    MIN_WINDOW,
    SettingsFormErrors,
    SettingsValues,
    format_height,
    parse_settings_form,
    parse_units_form,
    settings_to_form,
)
from tdee_calculator.units import (
    EnergyUnit,
    WeightUnit,
    format_density,
    format_rate,
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


def render_settings(
    request: Request,
    settings: Settings,
    values: SettingsValues | None = None,
    units: SettingsValues | None = None,
    errors: dict[str, str] | None = None,
    status_code: int = 200,
    saved: bool = False,
    notice: str | None = None,
) -> HTMLResponse:
    weight, energy = settings.weight_unit, settings.energy_unit
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "settings": settings,
            "form_values": settings_to_form(settings) if values is None else values,
            "unit_values": settings_to_form(settings) if units is None else units,
            "errors": errors or {},
            "saved": saved,
            "notice": notice,
            "weight_units": WeightUnit,
            "energy_units": EnergyUnit,
            "activity_labels": ACTIVITY_LABELS,
            "today": clock.today(),
            "height_min": MIN_HEIGHT_CM,
            "height_max": MAX_HEIGHT_CM,
            "height_limits": (
                f"{format_height(MIN_HEIGHT_CM, weight)} to "
                f"{format_height(MAX_HEIGHT_CM, weight)}"
            ),
            "weight_min": format_weight(MIN_WEIGHT_KG, weight),
            "weight_max": format_weight(MAX_WEIGHT_KG, weight),
            "rate_min": format_rate(MIN_RATE, weight),
            "rate_max": format_rate(MAX_RATE, weight),
            "window_min": MIN_WINDOW,
            "window_max": MAX_WINDOW,
            "density_min": format_density(MIN_DENSITY, weight, energy),
            "density_max": format_density(MAX_DENSITY, weight, energy),
            "default_window": Settings().tdee_window_days,
            "default_density": format_density(
                Settings().energy_density, weight, energy
            ),
        },
        status_code=status_code,
    )


@router.get("/settings")
def settings_page(
    request: Request, settings: SettingsDependency, saved: bool = False
) -> HTMLResponse:
    return render_settings(request, settings, saved=saved)


@router.post("/settings/units", response_model=None)
def update_units(
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    form: FormDependency,
) -> HTMLResponse | RedirectResponse:
    result = parse_units_form(form, settings)
    if isinstance(result, SettingsFormErrors):
        return render_settings(
            request, settings, units=form, errors=result.errors, status_code=422
        )
    save_settings(session, result)
    return RedirectResponse("/settings?saved=1", status_code=303)


@router.post("/settings", response_model=None)
def update_settings(
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    form: FormDependency,
) -> HTMLResponse | RedirectResponse:
    if not units_match(form, settings):
        return render_settings(
            request, settings, status_code=409, notice=STALE_UNITS_NOTICE
        )
    result = parse_settings_form(form, settings, clock.today())
    if isinstance(result, SettingsFormErrors):
        return render_settings(
            request, settings, values=form, errors=result.errors, status_code=422
        )
    save_settings(session, result)
    return RedirectResponse("/settings?saved=1", status_code=303)
