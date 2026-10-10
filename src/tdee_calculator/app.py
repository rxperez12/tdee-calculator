from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import sessionmaker
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.trustedhost import TrustedHostMiddleware

from tdee_calculator.config import Config, load_config
from tdee_calculator.db import make_engine, run_migrations
from tdee_calculator.routes import history, measurements, settings, today
from tdee_calculator.security import allowed_hosts, is_cross_origin
from tdee_calculator.web import PACKAGE_DIR


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
    application.include_router(today.router)
    application.include_router(history.router)
    application.include_router(measurements.router)
    application.include_router(settings.router)
    return application


app = create_app()
