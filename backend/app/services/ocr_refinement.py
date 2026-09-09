import statistics
from dataclasses import dataclass
from io import BytesIO
from typing import Literal

from PIL import Image, ImageFilter, ImageOps

from app.models.verification import (
    ApplicationData,
    ExtractedCandidates,
    FieldVerificationResult,
    OcrRefinementEvidence,
    RefinementBoundingBox,
    RefinementField,
    TextCandidate,
    VerificationResults,
)
from app.services.comparison import compare_application_data
from app.services.normalization import normalize_text
from app.services.ocr import (
    BoundingBox,
    OcrProcessingError,
    OcrResult,
    OcrService,
    OcrUnavailableError,
    RegionalOcrService,
)
from app.services.spatial_layout import OcrLine, overlaps_box, reconstruct_ocr_lines, union_boxes
from app.services.structured_extraction import extract_candidates

MAX_REGIONAL_OCR_CALLS = 3
MIN_REFINED_CONFIDENCE = 0.55


@dataclass(frozen=True, slots=True)
class RefinementPlan:
    field: RefinementField
    trigger: str
    crop: BoundingBox
    page_segmentation_mode: Literal[6, 7]
    full_image_candidates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RefinementOutcome:
    candidates: ExtractedCandidates
    results: VerificationResults
    evidence: tuple[OcrRefinementEvidence, ...]
    warnings: tuple[str, ...]
    invocation_count: int
    duration_ms: float


async def refine_ocr_candidates(
    *,
    ocr_service: OcrService,
    preprocessed_image: bytes,
    full_ocr: OcrResult,
    expected: ApplicationData,
    candidates: ExtractedCandidates,
    results: VerificationResults,
    excluded_regions: tuple[BoundingBox, ...] = (),
) -> RefinementOutcome:
    """Run at most three justified crop OCR calls and retain only stronger evidence."""

    if not isinstance(ocr_service, RegionalOcrService):
        return RefinementOutcome(candidates, results, (), (), 0, 0.0)

    plans = plan_regional_refinements(
        full_ocr,
        candidates=candidates,
        results=results,
        excluded_regions=excluded_regions,
    )[:MAX_REGIONAL_OCR_CALLS]
    selected_candidates = candidates
    selected_results = results
    evidence: list[OcrRefinementEvidence] = []
    warnings: list[str] = []
    invocations = 0
    duration_ms = 0.0

    for plan in plans:
        crop_data = crop_for_refinement(preprocessed_image, plan.crop)
        invocations += 1
        try:
            refined_ocr = await ocr_service.extract_region(
                crop_data,
                media_type="image/png",
                page_segmentation_mode=plan.page_segmentation_mode,
            )
        except (OcrProcessingError, OcrUnavailableError):
            warnings.append(
                f"Regional OCR refinement for {plan.field} failed; "
                "full-image evidence was retained."
            )
            continue

        duration_ms += refined_ocr.duration_ms
        refined_candidates = getattr(extract_candidates(refined_ocr), plan.field)
        mean_confidence = _mean_confidence(refined_ocr)
        trial_candidates = selected_candidates.model_copy(
            update={plan.field: refined_candidates},
            deep=True,
        )
        trial_results = compare_application_data(expected, trial_candidates)
        selected = _is_stronger_result(
            before=getattr(selected_results, plan.field),
            after=getattr(trial_results, plan.field),
            mean_confidence=mean_confidence,
        )
        evidence.append(
            OcrRefinementEvidence(
                field=plan.field,
                trigger=plan.trigger,
                full_image_candidates=list(plan.full_image_candidates),
                refined_text=refined_ocr.text,
                selected=selected,
                page_segmentation_mode=plan.page_segmentation_mode,
                mean_confidence=mean_confidence,
                duration_ms=refined_ocr.duration_ms,
                crop=RefinementBoundingBox(
                    left=plan.crop.left,
                    top=plan.crop.top,
                    width=plan.crop.width,
                    height=plan.crop.height,
                ),
            )
        )
        if selected:
            selected_candidates = trial_candidates
            selected_results = trial_results

    return RefinementOutcome(
        candidates=selected_candidates,
        results=selected_results,
        evidence=tuple(evidence),
        warnings=tuple(warnings),
        invocation_count=invocations,
        duration_ms=duration_ms,
    )


def plan_regional_refinements(
    full_ocr: OcrResult,
    *,
    candidates: ExtractedCandidates,
    results: VerificationResults,
    excluded_regions: tuple[BoundingBox, ...] = (),
) -> tuple[RefinementPlan, ...]:
    """Select bounded, image-derived crop opportunities without using expected text."""

    lines = [
        line
        for line in reconstruct_ocr_lines(full_ocr)
        if line.bounding_box is not None
        and not any(overlaps_box(line, excluded) for excluded in excluded_regions)
    ]
    plans: list[RefinementPlan] = []
    if results.net_contents.status == "not_found":
        volume = _volume_plan(full_ocr, lines, candidates)
        if volume is not None:
            plans.append(volume)
    if results.brand_name.status == "review" and candidates.brand_name:
        brand = _candidate_plan(
            full_ocr,
            lines,
            field="brand_name",
            candidate_values=candidates.brand_name,
            selected_raw=results.brand_name.extracted_raw,
        )
        if brand is not None:
            plans.append(brand)
    if results.class_type.status == "review" and candidates.class_type:
        class_type = _candidate_plan(
            full_ocr,
            lines,
            field="class_type",
            candidate_values=candidates.class_type,
            selected_raw=results.class_type.extracted_raw,
        )
        if class_type is not None:
            plans.append(class_type)
    return tuple(plans[:MAX_REGIONAL_OCR_CALLS])


def crop_for_refinement(image_data: bytes, crop: BoundingBox) -> bytes:
    """Crop existing OCR pixels, then apply bounded local contrast and sharpening."""

    with Image.open(BytesIO(image_data)) as source:
        image = source.convert("L")
        region = image.crop((crop.left, crop.top, crop.left + crop.width, crop.top + crop.height))
    region = ImageOps.autocontrast(region)
    region = region.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=2))
    output = BytesIO()
    region.save(output, format="PNG")
    region.close()
    return output.getvalue()


def _candidate_plan(
    full_ocr: OcrResult,
    lines: list[OcrLine],
    *,
    field: RefinementField,
    candidate_values: list[TextCandidate],
    selected_raw: str | None,
) -> RefinementPlan | None:
    primary = next(
        (candidate for candidate in candidate_values if candidate.raw_value == selected_raw),
        candidate_values[0],
    )
    by_number = {line.sequence_number: line for line in lines}
    primary_line = by_number.get(primary.line_number)
    if primary_line is None or primary_line.bounding_box is None:
        return None
    selected_lines = [primary_line]
    if field == "brand_name":
        selected_lines.extend(
            line
            for candidate in candidate_values
            if candidate is not primary
            and (line := by_number.get(candidate.line_number)) is not None
            and _same_display_region(primary_line, line)
        )
    if normalize_text(primary_line.text) != primary.normalized_value:
        selected_lines.extend(
            line
            for line in lines
            if line.sequence_number > primary_line.sequence_number
            and line.sequence_number <= primary_line.sequence_number + 2
            and line.panel_id == primary_line.panel_id
            and normalize_text(line.text) in primary.normalized_value
        )
    box = union_boxes([line.bounding_box for line in selected_lines])
    if box is None:
        return None
    crop = _expanded_box(
        box,
        full_ocr.image_width,
        full_ocr.image_height,
        vertical_margin_ratio=0.35 if field == "class_type" else 0.18,
    )
    line_count = len({line.sequence_number for line in selected_lines})
    mode = 6 if field == "brand_name" or line_count > 1 else 7
    return RefinementPlan(
        field=field,
        trigger=f"Full-image {field} comparison requires review.",
        crop=crop,
        page_segmentation_mode=mode,
        full_image_candidates=tuple(candidate.raw_value for candidate in candidate_values),
    )


def _volume_plan(
    full_ocr: OcrResult,
    lines: list[OcrLine],
    candidates: ExtractedCandidates,
) -> RefinementPlan | None:
    if not candidates.abv:
        return None
    by_number = {line.sequence_number: line for line in lines}
    abv_line = by_number.get(candidates.abv[0].line_number)
    if abv_line is None or abv_line.bounding_box is None:
        return None
    abv_box = abv_line.bounding_box
    occupied = {
        candidate.line_number
        for field in (
            candidates.brand_name,
            candidates.class_type,
            candidates.abv,
            candidates.producer_name,
            candidates.producer_address,
            candidates.country_origin,
        )
        for candidate in field
    }
    possible: list[tuple[float, OcrLine]] = []
    abv_center = abv_box.top + abv_box.height / 2
    for line in lines:
        box = line.bounding_box
        if (
            box is None
            or line.sequence_number in occupied
            or line.panel_id != abv_line.panel_id
            or box.width < max(abv_box.width * 0.5, full_ocr.image_width * 0.12)
            or abs((box.top + box.height / 2) - abv_center) > full_ocr.image_height * 0.3
            or "label with mandatory" in line.text.casefold()
        ):
            continue
        distance = abs((box.top + box.height / 2) - abv_center)
        possible.append((distance - min(box.width, abv_box.width) * 0.05, line))
    if not possible:
        return None
    _score, selected = min(possible, key=lambda item: item[0])
    box = selected.bounding_box
    if box is None:
        return None
    return RefinementPlan(
        field="net_contents",
        trigger="No full-image volume was found near a prominent lower-panel text region.",
        crop=_expanded_box(box, full_ocr.image_width, full_ocr.image_height),
        page_segmentation_mode=7,
        full_image_candidates=(),
    )


def _same_display_region(first: OcrLine, second: OcrLine) -> bool:
    if first.panel_id != second.panel_id:
        return False
    first_box = first.bounding_box
    second_box = second.bounding_box
    if first_box is None or second_box is None:
        return False
    first_center = first_box.top + first_box.height / 2
    second_center = second_box.top + second_box.height / 2
    return abs(first_center - second_center) <= max(first_box.height, second_box.height) * 1.5


def _expanded_box(
    box: BoundingBox,
    image_width: int,
    image_height: int,
    *,
    vertical_margin_ratio: float = 0.18,
) -> BoundingBox:
    horizontal_margin = max(16, round(box.width * 0.08))
    vertical_margin = max(12, round(box.height * vertical_margin_ratio))
    left = max(0, box.left - horizontal_margin)
    top = max(0, box.top - vertical_margin)
    right = min(image_width, box.left + box.width + horizontal_margin)
    bottom = min(image_height, box.top + box.height + vertical_margin)
    return BoundingBox(left=left, top=top, width=right - left, height=bottom - top)


def _mean_confidence(ocr: OcrResult) -> float | None:
    confidences = [region.confidence for region in ocr.regions if region.confidence is not None]
    return statistics.fmean(confidences) if confidences else None


def _is_stronger_result(
    *,
    before: FieldVerificationResult,
    after: FieldVerificationResult,
    mean_confidence: float | None,
) -> bool:
    if mean_confidence is None or mean_confidence < MIN_REFINED_CONFIDENCE:
        return False
    rank = {"not_found": 0, "mismatch": 1, "review": 2, "match": 3, "not_applicable": 0}
    return rank[after.status] > rank[before.status]
