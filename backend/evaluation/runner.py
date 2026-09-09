import asyncio
import math
import shutil
from collections import Counter, defaultdict
from statistics import median
from time import perf_counter
from typing import Any

from app.core.config import Settings
from app.services.comparison import compare_application_data
from app.services.government_warning import analyze_government_warning
from app.services.image_preprocessing import prepare_image
from app.services.normalization import normalize_volume
from app.services.structured_extraction import extract_candidates
from app.services.tesseract import TesseractOcrService
from evaluation.corpus import EvaluationCase, evaluation_cases, render_case


async def run_evaluation(
    cases: tuple[EvaluationCase, ...] | None = None,
) -> dict[str, Any]:
    selected_cases = cases or evaluation_cases()
    command = shutil.which("tesseract")
    if command is None:
        raise RuntimeError("Tesseract is required to run the evaluation corpus.")
    settings = Settings(environment="test", tesseract_command=command)
    service = TesseractOcrService(
        command=command,
        language=settings.tesseract_language,
        timeout_seconds=settings.ocr_timeout_seconds,
    )
    case_reports: list[dict[str, Any]] = []
    latencies: dict[str, list[float]] = defaultdict(list)
    actual_counts: Counter[str] = Counter()
    per_check: dict[str, Counter[str]] = defaultdict(Counter)
    false_matches = 0
    false_mismatches = 0
    missed_matches = 0
    exact_checks = 0
    failures = 0
    empty_ocr = 0

    for case in selected_cases:
        case_started = perf_counter()
        try:
            rendered = render_case(case)
            preprocessing_started = perf_counter()
            prepared = prepare_image(
                rendered.data,
                content_type=rendered.media_type,
                settings=settings,
            )
            preprocessing_ms = (perf_counter() - preprocessing_started) * 1_000
            ocr = await service.extract(prepared.data, media_type="image/png")
            analysis_started = perf_counter()
            candidates = extract_candidates(ocr.text)
            results = compare_application_data(case.application, candidates)
            warning = analyze_government_warning(
                ocr,
                preprocessed_image=prepared.visual_evidence_data,
                container_volume_ml=normalize_volume(case.application.net_contents),
            )
            analysis_ms = (perf_counter() - analysis_started) * 1_000
            total_ms = (perf_counter() - case_started) * 1_000
            if not ocr.text:
                empty_ocr += 1

            actual = _actual_statuses(results, warning)
            differences: list[dict[str, str]] = []
            for check, expected_status in case.expected.items():
                actual_status = actual[check]
                actual_counts[actual_status] += 1
                per_check[check][actual_status] += 1
                if actual_status == expected_status:
                    exact_checks += 1
                    continue
                differences.append(
                    {"check": check, "expected": expected_status, "actual": actual_status}
                )
                if actual_status == "match" and expected_status != "match":
                    false_matches += 1
                if actual_status == "mismatch" and expected_status != "mismatch":
                    false_mismatches += 1
                if expected_status == "match" and actual_status != "match":
                    missed_matches += 1

            latencies["preprocessing_ms"].append(preprocessing_ms)
            latencies["ocr_ms"].append(ocr.duration_ms)
            latencies["analysis_ms"].append(analysis_ms)
            latencies["total_ms"].append(total_ms)
            case_reports.append(
                {
                    "name": case.name,
                    "beverage_style": case.beverage_style,
                    "degradation": case.degradation,
                    "ocr_text": ocr.text,
                    "differences": differences,
                    "latency_ms": {
                        "preprocessing": round(preprocessing_ms, 3),
                        "ocr": round(ocr.duration_ms, 3),
                        "analysis": round(analysis_ms, 3),
                        "total": round(total_ms, 3),
                    },
                }
            )
        except Exception as exc:  # The harness reports failures instead of hiding later cases.
            failures += 1
            case_reports.append(
                {
                    "name": case.name,
                    "beverage_style": case.beverage_style,
                    "degradation": case.degradation,
                    "error": type(exc).__name__,
                    "differences": [],
                }
            )

    total_expectations = sum(len(case.expected) for case in selected_cases)
    return {
        "total_cases": len(selected_cases),
        "total_expectations": total_expectations,
        "exact_status_checks": exact_checks,
        "status_accuracy": round(exact_checks / total_expectations, 4) if total_expectations else 0,
        "false_confident_matches": false_matches,
        "false_mismatches": false_mismatches,
        "missed_matches": missed_matches,
        "review_count": actual_counts["review"],
        "not_found_count": actual_counts["not_found"],
        "ocr_or_processing_failures": failures,
        "empty_ocr_results": empty_ocr,
        "latency_ms": {
            name: _latency_summary(values) for name, values in sorted(latencies.items())
        },
        "per_check": {
            name: dict(sorted(counts.items())) for name, counts in sorted(per_check.items())
        },
        "cases": case_reports,
    }


def run_evaluation_sync() -> dict[str, Any]:
    return asyncio.run(run_evaluation())


def _actual_statuses(results: Any, warning: Any) -> dict[str, str]:
    statuses = {
        f"results.{field}": getattr(results, field).status
        for field in (
            "brand_name",
            "class_type",
            "abv",
            "net_contents",
            "producer_name",
            "producer_address",
            "country_origin",
        )
    }
    statuses.update(
        {
            f"warning.{name}": getattr(warning.checks, name).status
            for name in (
                "presence",
                "wording",
                "heading_capitalization",
                "heading_boldness",
                "body_not_bold",
                "continuous_statement",
                "separation",
                "legibility_contrast",
                "type_size",
                "characters_per_inch",
            )
        }
    )
    return statuses


def _latency_summary(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    p90_index = max(0, math.ceil(len(ordered) * 0.9) - 1)
    return {
        "median": round(median(ordered), 3),
        "p90": round(ordered[p90_index], 3),
        "slowest": round(ordered[-1], 3),
    }
