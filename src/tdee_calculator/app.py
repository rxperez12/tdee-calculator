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
from tdee_calculator.entry_form import EntryFormErrors, parse_entry_form
from tdee_calculator.models import Entry
from tdee_calculator.security import allowed_hosts, is_cross_origin

PACKAGE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")


def get_session(request: Request) -> Iterator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


SessionDependency = Annotated[Session, Depends(get_session)]


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
        errors: dict[str, str] | None = None,
        status_code: int = 200,
        saved: Date | None = None,
        conflict_date: Date | None = None,
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
                "is_update": is_update,
            },
            status_code=status_code,
        )

    @application.get("/")
    def home(
        request: Request,
        session: SessionDependency,
        date: Date | None = None,
        saved: Date | None = None,
    ) -> HTMLResponse:
        form_date = date or clock.today()
        entry = entries.get_entry(session, form_date)
        values = {
            "entry_date": form_date.isoformat(),
            "loaded_date": form_date.isoformat(),
            "weight_kg": (
                str(entry.weight_kg)
                if entry is not None and entry.weight_kg is not None
                else ""
            ),
            "calories": (
                str(entry.calories)
                if entry is not None and entry.calories is not None
                else ""
            ),
        }
        return render_home(request, session, values, saved=saved)

    @application.post("/entries", response_model=None)
    def save_entry(
        request: Request,
        session: SessionDependency,
        entry_date: Annotated[str, Form()] = "",
        loaded_date: Annotated[str, Form()] = "",
        weight_kg: Annotated[str, Form()] = "",
        calories: Annotated[str, Form()] = "",
    ) -> HTMLResponse | RedirectResponse:
        values = {
            "entry_date": entry_date,
            "loaded_date": loaded_date,
            "weight_kg": weight_kg,
            "calories": calories,
        }
        result = parse_entry_form(entry_date, weight_kg, calories, clock.today())
        if isinstance(result, EntryFormErrors):
            return render_home(request, session, values, result.errors, status_code=422)
        loaded: Date | None
        try:
            loaded = Date.fromisoformat(loaded_date)
        except ValueError:
            loaded = None
        if (
            result.date != loaded
            and entries.get_entry(session, result.date) is not None
        ):
            return render_home(
                request, session, values, status_code=409, conflict_date=result.date
            )
        entries.upsert_entry(session, result)
        return RedirectResponse(f"/?saved={result.date.isoformat()}", status_code=303)

    @application.post("/entries/{entry_date}/delete")
    def remove_entry(entry_date: Date, session: SessionDependency) -> RedirectResponse:
        entries.delete_entry(session, entry_date)
        return RedirectResponse("/", status_code=303)

    return application


app = create_app()
