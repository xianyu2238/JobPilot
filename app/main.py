"""Application factory and ASGI entry point."""

from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import Settings
from app.core.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    configure_logging(settings.log_level)
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="JobPilot AI 求职助手 API（阶段 0：工程初始化）",
    )
    application.state.settings = settings
    application.include_router(health_router)
    return application


app = create_app()
