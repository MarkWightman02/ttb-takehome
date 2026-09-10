import statistics
from dataclasses import dataclass
from difflib import SequenceMatcher
from io import BytesIO
from typing import Literal

from PIL import Image, ImageFilter, ImageOps

from app.models.verification import (
    ApplicationData,
    ExtractedCandidates,
    OcrRefinementEvidence,
    RefinementBoundingBox,
    RefinementField,
    TextCandidate,
    VerificationResults,
    VolumeCandidate,
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
TARGET_CROP_TEXT_HEIGHT = 48
OVERSIZED_CROP_TEXT_HEIGHT = 96


@dataclass(frozen=True, slots=True)
class RefinementPlan:
    field: RefinementField
    trigger: str
    crop: BoundingBox
    page_segmentation_mode: Literal[6, 7]
    full_image_candidates: tuple[str, ...]
    source_line_numbers: tuple[int, ...] = ()
    text_height: float | None = None
    retained_lines: tuple[OcrLine, ...] = ()


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
        crop_data = crop_for_refinement(preprocessed_image, plan.crop, text_height=plan.text_height)
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
        if (
            plan.retained_lines
            and len(reconstruct_ocr_lines(refined_ocr)) == 1
            and any(character.isalnum() for character in refined_ocr.text)
            and not any(
                normalize_text(line.text) in normalize_text(refined_ocr.text)
                for line in plan.retained_lines
            )
        ):
            # A smaller, already legible line can disappear when a display logo
            # is segmented as a block. Retain that independent full-image evidence.
            raw = " ".join([refined_ocr.text, *(line.text for line in plan.retained_lines)])
            refined_candidates = [
                TextCandidate(
                    raw_value=raw,
                    normalized_value=normalize_text(raw),
                    source_line=(
                        f"Regional OCR: {refined_ocr.text}\n"
                        "Retained full-image OCR: "
                        + " / ".join(line.text for line in plan.retained_lines)
                    ),
                    line_number=1,
                )
            ]
        mean_confidence = _mean_confidence(refined_ocr)
        trial_candidates = selected_candidates.model_copy(
            update={plan.field: refined_candidates},
            deep=True,
        )
        selected = _is_stronger_evidence(
            before=[
                candidate
                for candidate in getattr(selected_candidates, plan.field)
                if candidate.line_number in plan.source_line_numbers
            ],
            after=refined_candidates,
            full_ocr=full_ocr,
            refined_ocr=refined_ocr,
            retained_lines=plan.retained_lines,
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
            selected_results = compare_application_data(expected, trial_candidates)

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
    if candidates.brand_name and (
        results.brand_name.status == "review" or _has_weak_token(candidates.brand_name, full_ocr)
    ):
        brand = _candidate_plan(
            full_ocr,
            lines,
            field="brand_name",
            candidate_values=candidates.brand_name,
        )
        if brand is not None:
            plans.append(brand)
    if candidates.class_type and (
        results.class_type.status == "review" or _has_weak_token(candidates.class_type, full_ocr)
    ):
        class_type = _candidate_plan(
            full_ocr,
            lines,
            field="class_type",
            candidate_values=candidates.class_type,
        )
        if class_type is not None:
            plans.append(class_type)
    return tuple(
        plan
        for plan in plans[:MAX_REGIONAL_OCR_CALLS]
        if not any(
            plan.crop.left < region.left + region.width
            and plan.crop.left + plan.crop.width > region.left
            and plan.crop.top < region.top + region.height
            and plan.crop.top + plan.crop.height > region.top
            for region in excluded_regions
        )
    )


def crop_for_refinement(
    image_data: bytes, crop: BoundingBox, *, text_height: float | None = None
) -> bytes:
    """Crop existing OCR pixels, then apply bounded local contrast and sharpening."""

    with Image.open(BytesIO(image_data)) as source:
        image = source.convert("L")
        region = image.crop((crop.left, crop.top, crop.left + crop.width, crop.top + crop.height))
    if text_height is not None and text_height > OVERSIZED_CROP_TEXT_HEIGHT:
        scale = TARGET_CROP_TEXT_HEIGHT / text_height
        region = region.resize(
            (max(1, round(region.width * scale)), max(1, round(region.height * scale))),
            Image.Resampling.LANCZOS,
        )
        region = ImageOps.autocontrast(region)
    else:
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
) -> RefinementPlan | None:
    # Candidate order is image-derived. A comparison's closest expected value
    # must not decide which pixels receive another recognition attempt.
    primary = candidate_values[0]
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
    retained_lines: tuple[OcrLine, ...] = ()
    if field == "brand_name" and len(selected_lines) > 1:
        smaller = [line for line in selected_lines if line is not primary_line]
        if all(
            line.top is not None
            and line.top >= primary_line.top + primary_line.height
            and (line.approximate_line_height or 0) * 2.5 < primary_line.height
            and line.mean_confidence is not None
            and line.mean_confidence >= 0.85
            for line in smaller
        ):
            retained_lines = tuple(sorted(smaller, key=lambda line: line.top or 0))
    crop = _expanded_box(
        box,
        full_ocr.image_width,
        full_ocr.image_height,
        vertical_margin_ratio=0.35 if field == "class_type" else 0.18,
        minimum_horizontal_margin=primary_line.height * 0.5 if retained_lines else 0,
    )
    line_count = len({line.sequence_number for line in selected_lines})
    mode = 6 if field == "brand_name" or line_count > 1 else 7
    return RefinementPlan(
        field=field,
        trigger=f"Full-image {field} has uncertain text or weak token confidence.",
        crop=crop,
        page_segmentation_mode=mode,
        full_image_candidates=tuple(candidate.raw_value for candidate in candidate_values),
        source_line_numbers=tuple(line.sequence_number for line in selected_lines),
        text_height=(
            statistics.median(
                word.bounding_box.height
                for line in selected_lines
                for word in line.words
                if word.bounding_box is not None
            )
            if not retained_lines
            else None
        ),
        retained_lines=retained_lines,
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
    minimum_horizontal_margin: float = 0,
) -> BoundingBox:
    horizontal_margin = max(16, round(box.width * 0.08), round(minimum_horizontal_margin))
    vertical_margin = max(12, round(box.height * vertical_margin_ratio))
    left = max(0, box.left - horizontal_margin)
    top = max(0, box.top - vertical_margin)
    right = min(image_width, box.left + box.width + horizontal_margin)
    bottom = min(image_height, box.top + box.height + vertical_margin)
    return BoundingBox(left=left, top=top, width=right - left, height=bottom - top)


def _mean_confidence(ocr: OcrResult) -> float | None:
    confidences = [region.confidence for region in ocr.regions if region.confidence is not None]
    return statistics.fmean(confidences) if confidences else None


def _is_stronger_evidence(
    *,
    before: list[TextCandidate] | list[VolumeCandidate],
    after: list[TextCandidate] | list[VolumeCandidate],
    full_ocr: OcrResult,
    refined_ocr: OcrResult,
    retained_lines: tuple[OcrLine, ...] = (),
) -> bool:
    """Select evidence before comparing it with the application, including mismatches."""
    if len(after) != 1:
        return False
    after_conf = _candidate_confidences(after, refined_ocr)
    after_conf.extend(
        word.confidence
        for line in retained_lines
        for word in line.words
        if word.confidence is not None
    )
    if not after_conf or min(after_conf) < MIN_REFINED_CONFIDENCE:
        return False
    if not before:
        return True  # A single syntactically valid, legible volume where none existed.
    before_text = " ".join(candidate.raw_value for candidate in before)
    after_text = after[0].raw_value
    before_norm, after_norm = normalize_text(before_text), normalize_text(after_text)
    if (
        len(after_norm) < len(before_norm) * 0.75
        or SequenceMatcher(None, before_norm, after_norm).ratio() < 0.65
    ):
        return False  # Do not replace a complete field with a fragment/unrelated crop.
    before_conf = _candidate_confidences(before, full_ocr)
    if not before_conf:
        return False
    return (
        statistics.fmean(after_conf) >= statistics.fmean(before_conf) + 0.02
        or min(after_conf) >= min(before_conf) + 0.10
    )


def _candidate_confidences(
    candidates: list[TextCandidate] | list[VolumeCandidate], ocr: OcrResult
) -> list[float]:
    # Only candidate tokens contribute. A decorative trailing glyph must neither
    # hide a damaged content token in the mean nor veto an otherwise legible line.
    lines = reconstruct_ocr_lines(ocr)
    relevant = []
    for candidate in candidates:
        for line in lines:
            if line.sequence_number == candidate.line_number or (
                candidate.line_number < line.sequence_number <= candidate.line_number + 2
                and normalize_text(line.text) in normalize_text(candidate.raw_value)
            ):
                relevant.extend(line.words)
    tokens = {
        token for candidate in candidates for token in normalize_text(candidate.raw_value).split()
    }
    return [
        word.confidence if word.confidence is not None else 0.0
        for word in relevant
        if (normalized := normalize_text(word.text)) and set(normalized.split()) <= tokens
    ]


def _has_weak_token(candidates: list[TextCandidate], ocr: OcrResult) -> bool:
    confidences = _candidate_confidences(candidates, ocr)
    return bool(confidences) and min(confidences) < 0.80
