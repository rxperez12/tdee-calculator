from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from tdee_calculator.config import Config, load_config
from tdee_calculator.db import make_engine, run_migrations
from tdee_calculator.models import Entry


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
    application.mount(
        "/static",
        StaticFiles(directory=PACKAGE_DIR / "static"),
        name="static",
    )

    @application.get("/")
    def home(request: Request, session: SessionDependency):
        entry_count = session.scalar(select(func.count()).select_from(Entry)) or 0
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"entry_count": entry_count},
        )

    return application


app = create_app()
