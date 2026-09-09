import json
import math
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any

from PIL import Image

from app.core.config import Settings
from app.models.verification import ApplicationData
from app.services.comparison import compare_application_data
from app.services.government_warning import analyze_government_warning
from app.services.image_preprocessing import FORMAT_MEDIA_TYPES, prepare_image
from app.services.normalization import normalize_volume
from app.services.ocr import BoundingBox
from app.services.ocr_refinement import refine_ocr_candidates
from app.services.structured_extraction import extract_candidates
from app.services.tesseract import TesseractOcrService

SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
FIELD_NAMES = (
    "brand_name",
    "class_type",
    "abv",
    "net_contents",
    "producer_name",
    "producer_address",
    "country_origin",
)
STATUSES = ("match", "review", "mismatch", "not_found", "not_applicable")


@dataclass(frozen=True, slots=True)
class RealLabelCase:
    name: str
    image_path: Path
    metadata_path: Path
    application: ApplicationData


def discover_real_label_cases(examples_dir: Path) -> tuple[RealLabelCase, ...]:
    """Discover supported images with same-stem application-data JSON files."""

    if not examples_dir.is_dir():
        raise ValueError(f"Real-label directory does not exist: {examples_dir}")
    images = sorted(
        path
        for path in examples_dir.iterdir()
        if path.is_file() and path.suffix.casefold() in SUPPORTED_IMAGE_SUFFIXES
    )
    if not images:
        raise ValueError(f"No supported real-label images were found in {examples_dir}")

    cases: list[RealLabelCase] = []
    for image_path in images:
        metadata_path = image_path.with_suffix(".json")
        if not metadata_path.is_file():
            raise ValueError(f"Missing application data for {image_path.name}")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        cases.append(
            RealLabelCase(
                name=image_path.stem,
                image_path=image_path,
                metadata_path=metadata_path,
                application=_application_data(metadata),
            )
        )
    return tuple(cases)


async def run_real_label_evaluation(examples_dir: Path) -> dict[str, Any]:
    """Run each real fixture through full-image OCR and bounded refinement."""

    cases = discover_real_label_cases(examples_dir)
    command = shutil.which("tesseract")
    if command is None:
        raise RuntimeError("Tesseract is required to evaluate real labels.")
    settings = Settings(environment="test", tesseract_command=command)
    service = TesseractOcrService(
        command=command,
        language=settings.tesseract_language,
        timeout_seconds=settings.ocr_timeout_seconds,
    )
    reports: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    warning_status_counts: Counter[str] = Counter()
    latencies: dict[str, list[float]] = defaultdict(list)
    false_confident_matches = 0
    missed_expected_matches = 0
    ocr_failures = 0
    processing_failures = 0
    ocr_invocations = 0
    ocr_calls_per_case: list[float] = []

    for case in cases:
        started = perf_counter()
        stage = "preprocessing"
        try:
            image_data = case.image_path.read_bytes()
            source_format, media_type = _decoded_media_type(image_data)
            preprocessing_started = perf_counter()
            prepared = prepare_image(
                image_data,
                content_type=media_type,
                settings=settings,
            )
            preprocessing_ms = (perf_counter() - preprocessing_started) * 1_000
            ocr_invocations += 1
            stage = "ocr"
            ocr = await service.extract(prepared.data, media_type="image/png")
            stage = "analysis"
            analysis_started = perf_counter()
            warning = analyze_government_warning(
                ocr,
                preprocessed_image=prepared.visual_evidence_data,
                container_volume_ml=normalize_volume(case.application.net_contents),
            )
            excluded_regions = ()
            if warning.bounding_box is not None:
                excluded_regions = (
                    BoundingBox(
                        left=warning.bounding_box.left,
                        top=warning.bounding_box.top,
                        width=warning.bounding_box.width,
                        height=warning.bounding_box.height,
                    ),
                )
            initial_candidates = extract_candidates(ocr, excluded_regions=excluded_regions)
            initial_results = compare_application_data(case.application, initial_candidates)
            refinement = await refine_ocr_candidates(
                ocr_service=service,
                preprocessed_image=prepared.data,
                full_ocr=ocr,
                expected=case.application,
                candidates=initial_candidates,
                results=initial_results,
                excluded_regions=excluded_regions,
            )
            candidates = refinement.candidates
            results = refinement.results
            ocr_invocations += refinement.invocation_count
            case_ocr_calls = 1 + refinement.invocation_count
            ocr_calls_per_case.append(case_ocr_calls)
            analysis_ms = (perf_counter() - analysis_started) * 1_000
            total_ms = (perf_counter() - started) * 1_000

            for field in FIELD_NAMES:
                result = getattr(results, field)
                status_counts[result.status] += 1
                if _is_expected_check(case.application, field) and result.status != "match":
                    missed_expected_matches += 1
                if result.status == "match" and not _normalized_values_agree(result):
                    false_confident_matches += 1
            for check in type(warning.checks).model_fields:
                warning_status_counts[getattr(warning.checks, check).status] += 1

            latencies["preprocessing_ms"].append(preprocessing_ms)
            latencies["full_image_ocr_ms"].append(ocr.duration_ms)
            latencies["refinement_ms"].append(refinement.duration_ms)
            latencies["ocr_ms"].append(ocr.duration_ms + refinement.duration_ms)
            latencies["analysis_ms"].append(analysis_ms)
            latencies["total_ms"].append(total_ms)
            reports.append(
                {
                    "name": case.name,
                    "image": case.image_path.name,
                    "metadata": case.metadata_path.name,
                    "source_format": source_format,
                    "extension_matches_content": _extension_matches(
                        case.image_path.suffix, source_format
                    ),
                    "expected": case.application.model_dump(mode="json"),
                    "ocr_text": ocr.text,
                    "initial_candidates": initial_candidates.model_dump(mode="json"),
                    "initial_results": initial_results.model_dump(mode="json"),
                    "candidates": candidates.model_dump(mode="json"),
                    "results": results.model_dump(mode="json"),
                    "ocr_invocation_count": case_ocr_calls,
                    "ocr_refinements": [
                        item.model_dump(mode="json") for item in refinement.evidence
                    ],
                    "government_warning": warning.model_dump(mode="json"),
                    "warnings": [
                        *prepared.warnings,
                        *ocr.warnings,
                        *refinement.warnings,
                    ],
                    "latency_ms": {
                        "preprocessing": round(preprocessing_ms, 3),
                        "full_image_ocr": round(ocr.duration_ms, 3),
                        "refinement": round(refinement.duration_ms, 3),
                        "ocr": round(ocr.duration_ms + refinement.duration_ms, 3),
                        "analysis": round(analysis_ms, 3),
                        "total": round(total_ms, 3),
                    },
                }
            )
        except Exception as exc:  # Keep later fixtures visible when one case fails.
            if stage == "ocr":
                ocr_failures += 1
            else:
                processing_failures += 1
            reports.append(
                {
                    "name": case.name,
                    "image": case.image_path.name,
                    "metadata": case.metadata_path.name,
                    "expected": case.application.model_dump(mode="json"),
                    "error": type(exc).__name__,
                    "message": str(exc),
                }
            )

    return {
        "total_cases": len(cases),
        "ocr_invocations": ocr_invocations,
        "ocr_calls_per_case": _latency_summary(ocr_calls_per_case),
        "field_status_counts": {status: status_counts[status] for status in STATUSES},
        "warning_status_counts": {status: warning_status_counts[status] for status in STATUSES},
        "false_confident_matches": false_confident_matches,
        "missed_expected_matches": missed_expected_matches,
        "ocr_failures": ocr_failures,
        "processing_failures": processing_failures,
        "latency_ms": {
            name: _latency_summary(values) for name, values in sorted(latencies.items())
        },
        "cases": reports,
    }


def _application_data(metadata: dict[str, Any]) -> ApplicationData:
    imported = metadata.get("imported_product", metadata.get("imported"))
    if not isinstance(imported, bool):
        raise ValueError("Application data must contain a boolean imported value.")
    return ApplicationData(
        brand_name=_required(metadata, "brand_name", "brand"),
        class_type=_required(metadata, "class_type"),
        abv=_required(metadata, "abv"),
        net_contents=_required(metadata, "net_contents"),
        producer_name=_required(metadata, "producer_name"),
        producer_address=_required(metadata, "producer_address"),
        imported_product=imported,
        country_origin=(
            metadata.get("country_origin", metadata.get("country_of_origin")) if imported else None
        ),
    )


def _required(metadata: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = metadata.get(name)
        if value is not None:
            return value
    raise ValueError(f"Application data is missing {names[0]}.")


def _decoded_media_type(data: bytes) -> tuple[str, str]:
    with Image.open(BytesIO(data)) as image:
        image_format = (image.format or "").upper()
    media_type = FORMAT_MEDIA_TYPES.get(image_format)
    if media_type is None:
        raise ValueError(f"Unsupported decoded image format: {image_format or 'unknown'}")
    return image_format, media_type


def _extension_matches(extension: str, image_format: str) -> bool:
    expected = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}
    return expected.get(extension.casefold()) == image_format


def _is_expected_check(application: ApplicationData, field: str) -> bool:
    return field != "country_origin" or application.imported_product


def _normalized_values_agree(result: Any) -> bool:
    return result.expected_normalized == result.extracted_normalized


def _latency_summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"median": 0, "p90": 0, "slowest": 0}
    ordered = sorted(values)
    p90_index = max(0, math.ceil(len(ordered) * 0.9) - 1)
    return {
        "median": round(median(ordered), 3),
        "p90": round(ordered[p90_index], 3),
        "slowest": round(ordered[-1], 3),
    }
