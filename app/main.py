"""Application factory and ASGI entry point."""

import logging
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.resumes import router as resumes_router
from app.core.config import Settings
from app.core.errors import AppError
from app.core.llm import ModelClient
from app.core.logging import configure_logging
from app.repositories.memory import MemoryRepository
from app.services.ocr_service import LocalOCR
from app.services.resume_generation_service import ResumeGenerationService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    configure_logging(settings.log_level)
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="JobPilot：PDF/PNG/JPG 简历解析与修改学习建议",
    )
    application.state.settings = settings
    application.state.store = MemoryRepository(settings.store_capacity, settings.store_ttl_seconds)
    application.state.model = ModelClient(settings)
    application.state.ocr = LocalOCR(settings)
    application.state.resume_generator = ResumeGenerationService(settings, application.state.store)

    def error(request: Request, status: int, code: str, message: str):
        return JSONResponse(status_code=status, content={
            "code": code, "message": message, "request_id": getattr(request.state, "request_id", "")
        })

    @application.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        return error(request, exc.status, exc.code, exc.message)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return error(request, 422, "INPUT_INVALID", "参数缺失、类型错误或长度超限，请检查输入。")

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error(request, exc.status_code, "HTTP_ERROR", "请求地址、方法或上传格式不正确。")

    @application.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = uuid4().hex
        started = time.monotonic()
        try:
            length = request.headers.get("content-length", "0")
            if not length.isdigit():
                response = error(request, 400, "INPUT_INVALID", "请求长度无效。")
            elif int(length) > settings.max_file_mb * 1024 * 1024 + 1024 * 1024:
                response = error(request, 413, "FILE_TOO_LARGE", "请求内容超过上传限制。")
            else:
                response = await call_next(request)
        except Exception:
            logging.getLogger("jobpilot").error("request_failed request_id=%s", request.state.request_id)
            response = error(request, 500, "INTERNAL_ERROR", "服务处理失败，请使用请求编号排查或稍后重试。")
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        logging.getLogger("jobpilot").info(
            "request_id=%s method=%s status=%s duration_ms=%.0f",
            request.state.request_id, request.method, response.status_code, (time.monotonic() - started) * 1000,
        )
        return response

    application.include_router(health_router)
    application.include_router(resumes_router)
    application.include_router(jobs_router)
    return application


app = create_app()
