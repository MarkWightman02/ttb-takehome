import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.labels import router as labels_router
from app.core.config import Settings
from app.core.errors import register_exception_handlers
from app.core.frontend import mount_frontend
from app.core.logging import configure_logging
from app.services.ocr import OcrService
from app.services.tesseract import TesseractOcrService

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, ocr_service: OcrService | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Starting TTB Label Verification environment=%s", settings.environment)
        yield
        logger.info("Stopping TTB Label Verification")

    app = FastAPI(
        title="TTB Label Verification",
        version="0.1.0",
        description="Standalone prototype for request-scoped alcohol label OCR.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.ocr_service = ocr_service or TesseractOcrService(
        command=settings.tesseract_command,
        language=settings.tesseract_language,
        timeout_seconds=settings.ocr_timeout_seconds,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(labels_router)
    if settings.frontend_dist is not None:
        mount_frontend(app, settings.frontend_dist)
    return app


app = create_app()
