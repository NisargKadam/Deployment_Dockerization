"""FastAPI application factory and local process entry point."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.routes import router
from app.config import settings
from app.logging_conf import configure_logging
from app.telemetry import get_langsmith_client

configure_logging(settings.log_level)
logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
    logger.info(
        "application started",
        extra={"event": "application.started", "service": settings.app_name},
    )
    yield
    if client := get_langsmith_client():
        await asyncio.to_thread(client.flush, timeout=5)
    logger.info(
        "application stopped",
        extra={"event": "application.stopped", "service": settings.app_name},
    )


def create_app() -> FastAPI:
    application = FastAPI(title="Humanizer Agent", version=__version__, lifespan=lifespan)
    application.state.settings = settings
    application.include_router(router)
    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @application.get("/", include_in_schema=False)
    async def user_interface() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @application.get("/guide", include_in_schema=False)
    async def classroom_guide() -> FileResponse:
        return FileResponse(STATIC_DIR / "guide.html")

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.port, log_config=None)
