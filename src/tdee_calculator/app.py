from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import date as Date
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import (
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.trustedhost import TrustedHostMiddleware

from tdee_calculator import clock, entries
from tdee_calculator.config import Config, load_config
from tdee_calculator.db import make_engine, run_migrations
from tdee_calculator.entry_form import (
    MAX_CALORIES,
    MAX_WEIGHT_KG,
    MIN_CALORIES,
    MIN_WEIGHT_KG,
    EntryFormErrors,
    parse_entry_form,
)
from tdee_calculator.models import Entry
from tdee_calculator.security import allowed_hosts, is_cross_origin
from tdee_calculator.settings import Settings, load_settings, save_settings
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
    format_energy,
    format_rate,
    format_weight,
)

PACKAGE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")
templates.env.filters.update(
    weight=format_weight, energy=format_energy, rate=format_rate, density=format_density
)

STALE_UNITS_NOTICE = (
    "Your units changed since this page loaded. Nothing was saved. "
    "Check the values and submit again."
)


def get_session(request: Request) -> Iterator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


SessionDependency = Annotated[Session, Depends(get_session)]


def current_settings(session: SessionDependency) -> Settings:
    return load_settings(session)


SettingsDependency = Annotated[Settings, Depends(current_settings)]


async def get_form_values(request: Request) -> SettingsValues:
    return {
        key: value
        for key, value in (await request.form()).items()
        if isinstance(value, str)
    }


FormDependency = Annotated[SettingsValues, Depends(get_form_values)]


def units_match(values: dict[str, str], settings: Settings) -> bool:
    return (
        values.get("weight_unit") == settings.weight_unit.value
        and values.get("energy_unit") == settings.energy_unit.value
    )


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


def create_app(config: Config | None = None) -> FastAPI:
    app_config = config or load_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        run_migrations(app_config)
        engine = make_engine(app_config)
        app.state.session_factory = sessionmaker(engine)
        try:
            yield
        finally:
            engine.dispose()

    application = FastAPI(lifespan=lifespan)

    @application.middleware("http")
    async def protect_cross_origin(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if is_cross_origin(
            request.method,
            request.headers.get("host"),
            request.headers.get("origin"),
            request.headers.get("sec-fetch-site"),
        ):
            return PlainTextResponse("Cross-origin request refused", status_code=403)
        return await call_next(request)

    application.add_middleware(
        TrustedHostMiddleware, allowed_hosts=allowed_hosts(app_config)
    )
    application.mount(
        "/static",
        StaticFiles(directory=PACKAGE_DIR / "static"),
        name="static",
    )

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
    ) -> HTMLResponse:
        entry_count = session.scalar(select(func.count()).select_from(Entry)) or 0
        try:
            form_date = Date.fromisoformat(form_values["entry_date"])
        except ValueError:
            is_update = False
        else:
            is_update = entries.get_entry(session, form_date) is not None
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "entry_count": entry_count,
                "recent_entries": entries.recent_entries(session),
                "form_values": form_values,
                "errors": errors or {},
                "today": clock.today(),
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

    @application.get("/")
    def home(
        request: Request,
        session: SessionDependency,
        settings: SettingsDependency,
        date: Date | None = None,
        saved: Date | None = None,
    ) -> HTMLResponse:
        form_date = date or clock.today()
        values = entry_values(session, form_date, settings)
        return render_home(request, session, values, settings, saved=saved)

    @application.post("/entries", response_model=None)
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

    @application.post("/entries/{entry_date}/delete")
    def remove_entry(entry_date: Date, session: SessionDependency) -> RedirectResponse:
        entries.delete_entry(session, entry_date)
        return RedirectResponse("/", status_code=303)

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

    @application.get("/settings")
    def settings_page(
        request: Request, settings: SettingsDependency, saved: bool = False
    ) -> HTMLResponse:
        return render_settings(request, settings, saved=saved)

    @application.post("/settings/units", response_model=None)
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

    @application.post("/settings", response_model=None)
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

    return application


app = create_app()
