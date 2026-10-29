from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db import build_engine, get_session


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.engine = build_engine(config)
        try:
            yield
        finally:
            app.state.engine.dispose()

    app = FastAPI(
        title="ISE Day API",
        version="0.1.0",
        docs_url="/api/docs" if config.app_env != "production" else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if config.app_env != "production" else None,
        lifespan=lifespan,
    )

    @app.get("/api/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/health/ready", tags=["health"])
    def ready(
        response: Response,
        session: Annotated[Session, Depends(get_session)],
    ) -> dict[str, str]:
        response.headers["Cache-Control"] = "no-store"
        try:
            session.execute(text("SELECT 1"))
        except SQLAlchemyError:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "unavailable", "database": "unavailable"}
        return {"status": "ok", "database": "ok"}

    return app
