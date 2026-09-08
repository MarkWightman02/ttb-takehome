import asyncio
import logging
from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, File, Request, UploadFile

from app.core.errors import ApiError
from app.models.errors import ErrorResponse
from app.models.ocr import LabelOcrResponse, OcrImageMetadata
from app.services.image_preprocessing import normalize_media_type, prepare_image
from app.services.ocr import OcrProcessingError, OcrService, OcrUnavailableError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/labels", tags=["labels"])
READ_CHUNK_BYTES = 1024 * 1024


def get_ocr_service(request: Request) -> OcrService:
    return request.app.state.ocr_service


@router.post(
    "/ocr",
    response_model=LabelOcrResponse,
    responses={
        400: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def extract_label_text(
    request: Request,
    files: Annotated[list[UploadFile] | None, File(alias="file")] = None,
) -> LabelOcrResponse:
    if not files:
        raise ApiError(400, "missing_file", "Choose one label image to process.")
    if len(files) != 1:
        await _close_uploads(files)
        raise ApiError(400, "multiple_files", "Upload exactly one label image at a time.")

    upload = files[0]
    started = perf_counter()
    try:
        normalize_media_type(upload.content_type)
        data = await _read_upload(upload, request.app.state.settings.max_upload_bytes)
        prepared = await asyncio.to_thread(
            prepare_image,
            data,
            content_type=upload.content_type,
            settings=request.app.state.settings,
        )
        try:
            result = await get_ocr_service(request).extract(
                prepared.data,
                media_type="image/png",
            )
        except OcrUnavailableError as exc:
            raise ApiError(
                503,
                "ocr_unavailable",
                "Local OCR is unavailable. Install Tesseract and try again.",
            ) from exc
        except OcrProcessingError as exc:
            raise ApiError(
                500,
                "ocr_processing_failed",
                "The image could not be processed by OCR. Try another image.",
            ) from exc

        duration_ms = (perf_counter() - started) * 1_000
        combined_warnings = list(dict.fromkeys((*prepared.warnings, *result.warnings)))
        logger.info(
            "Label OCR completed engine=%s duration_ms=%.1f width=%s height=%s format=%s",
            result.engine_name,
            duration_ms,
            prepared.original_width,
            prepared.original_height,
            prepared.original_format,
        )
        return LabelOcrResponse(
            raw_text=result.text,
            engine=result.engine_name,
            processing_duration_ms=duration_ms,
            ocr_duration_ms=result.duration_ms,
            warnings=combined_warnings,
            image=OcrImageMetadata(
                width=prepared.original_width,
                height=prepared.original_height,
                format=prepared.original_format,
            ),
        )
    finally:
        await upload.close()


async def _read_upload(upload: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while chunk := await upload.read(READ_CHUNK_BYTES):
        size += len(chunk)
        if size > max_bytes:
            max_megabytes = max_bytes // (1024 * 1024)
            raise ApiError(
                413,
                "file_too_large",
                f"The image is too large. The maximum upload size is {max_megabytes} MB.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


async def _close_uploads(uploads: list[UploadFile]) -> None:
    for upload in uploads:
        await upload.close()
