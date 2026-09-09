import asyncio
import logging
from dataclasses import dataclass
from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile

from app.core.errors import ApiError
from app.models.errors import ErrorResponse
from app.models.ocr import LabelOcrResponse, OcrImageMetadata
from app.models.verification import ApplicationData, LabelVerificationResponse
from app.services.comparison import compare_application_data, overall_summary
from app.services.image_preprocessing import PreparedImage, normalize_media_type, prepare_image
from app.services.normalization import normalize_volume
from app.services.ocr import OcrProcessingError, OcrResult, OcrService, OcrUnavailableError
from app.services.structured_extraction import extract_candidates

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/labels", tags=["labels"])
READ_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class ProcessedLabel:
    prepared: PreparedImage
    ocr_result: OcrResult
    processing_duration_ms: float
    warnings: list[str]


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
    upload = await _single_upload(files)
    processed = await _process_upload(request, upload)
    prepared = processed.prepared
    result = processed.ocr_result
    return LabelOcrResponse(
        raw_text=result.text,
        engine=result.engine_name,
        processing_duration_ms=processed.processing_duration_ms,
        ocr_duration_ms=result.duration_ms,
        warnings=processed.warnings,
        image=OcrImageMetadata(
            width=prepared.original_width,
            height=prepared.original_height,
            format=prepared.original_format,
        ),
    )


@router.post(
    "/verify",
    response_model=LabelVerificationResponse,
    responses={
        400: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def verify_label(
    request: Request,
    brand_name: Annotated[str, Form(min_length=1, max_length=200)],
    class_type: Annotated[str, Form(min_length=1, max_length=200)],
    abv: Annotated[float, Form(gt=0, le=100)],
    net_contents: Annotated[str, Form(min_length=1, max_length=100)],
    files: Annotated[list[UploadFile] | None, File(alias="file")] = None,
) -> LabelVerificationResponse:
    if not brand_name.strip() or not class_type.strip() or not net_contents.strip():
        raise ApiError(400, "invalid_application_data", "Enter all four application fields.")
    expected = ApplicationData(
        brand_name=brand_name.strip(),
        class_type=class_type.strip(),
        abv=abv,
        net_contents=net_contents.strip(),
    )
    try:
        normalize_volume(expected.net_contents)
    except ValueError as exc:
        raise ApiError(400, "invalid_net_contents", str(exc)) from exc

    upload = await _single_upload(files)
    started = perf_counter()
    processed = await _process_upload(request, upload)
    candidates = extract_candidates(processed.ocr_result.text)
    results = compare_application_data(expected, candidates)
    prepared = processed.prepared
    return LabelVerificationResponse(
        expected=expected,
        candidates=candidates,
        results=results,
        overall_summary=overall_summary(results),
        raw_text=processed.ocr_result.text,
        engine=processed.ocr_result.engine_name,
        total_verification_duration_ms=(perf_counter() - started) * 1_000,
        ocr_duration_ms=processed.ocr_result.duration_ms,
        warnings=processed.warnings,
        image=OcrImageMetadata(
            width=prepared.original_width,
            height=prepared.original_height,
            format=prepared.original_format,
        ),
    )


async def _single_upload(files: list[UploadFile] | None) -> UploadFile:
    if not files:
        raise ApiError(400, "missing_file", "Choose one label image to process.")
    if len(files) != 1:
        await _close_uploads(files)
        raise ApiError(400, "multiple_files", "Upload exactly one label image at a time.")
    return files[0]


async def _process_upload(request: Request, upload: UploadFile) -> ProcessedLabel:
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
        return ProcessedLabel(
            prepared=prepared,
            ocr_result=result,
            processing_duration_ms=duration_ms,
            warnings=combined_warnings,
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
