import math
import re
import statistics
import unicodedata
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from io import BytesIO
from time import perf_counter

from PIL import Image

from app.models.verification import (
    GovernmentWarningAnalysis,
    GovernmentWarningChecks,
    WarningBoundingBox,
    WarningCheck,
)
from app.services.government_warning_rules import (
    GOVERNMENT_WARNING_HEADING,
    PRESCRIBED_GOVERNMENT_WARNING,
    physical_warning_requirement,
)
from app.services.ocr import BoundingBox, OcrResult, TextRegion
from app.services.spatial_layout import OcrLine, reconstruct_ocr_lines

WORD_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
CLAUSE_ONE_MARKER = re.compile(r"\(\s*1\s*\)")
CLAUSE_TWO_MARKER = re.compile(r"\(\s*2\s*\)")
COMMON_OCR_CHARACTERS = str.maketrans({"0": "o", "|": "l"})
CLAUSE_ONE_ANCHOR = ("according", "to", "the", "surgeon", "general")
CLAUSE_TWO_ANCHOR = ("consumption", "of", "alcoholic", "beverages")
LOW_CONFIDENCE_DIFFERENCE = 0.75
MINIMUM_REVIEW_TOKEN_SIMILARITY = 0.85


@dataclass(frozen=True, slots=True)
class LocalizedWarning:
    text: str
    regions: tuple[TextRegion, ...]
    region_indexes: frozenset[int]
    source_lines: tuple[str, ...]
    bounding_box: BoundingBox | None
    mean_confidence: float | None
    exact_heading_anchor: bool
    distinctive_anchor: bool


def analyze_government_warning(
    ocr_result: OcrResult,
    *,
    preprocessed_image: bytes,
    container_volume_ml: float,
) -> GovernmentWarningAnalysis:
    started = perf_counter()
    localized = _localize_warning(ocr_result)
    requirement = physical_warning_requirement(container_volume_ml)

    presence = _presence_check(localized)
    wording = _wording_check(localized)
    capitalization = _capitalization_check(localized)
    heading_boldness, body_not_bold = _visual_weight_checks(localized, preprocessed_image)
    continuity = _continuity_check(localized)
    separation = _separation_check(localized, ocr_result.regions)
    contrast = _contrast_check(localized, preprocessed_image)
    type_size = WarningCheck(
        status="review",
        explanation=(
            f"A minimum type size of {requirement.minimum_type_size_mm} mm applies, but "
            "physical type height cannot be established from image pixels without a "
            "trustworthy physical scale."
        ),
        evidence=["27 CFR 16.22(b)"],
        measurements={
            "container_volume_ml": container_volume_ml,
            "required_minimum_mm": requirement.minimum_type_size_mm,
            "physical_scale_available": False,
        },
    )
    characters_per_inch = WarningCheck(
        status="review",
        explanation=(
            f"The applicable limit is {requirement.maximum_characters_per_inch} "
            "characters per inch, but pixel width does not establish physical inches "
            "without a trustworthy scale."
        ),
        evidence=["27 CFR 16.22(a)(4)"],
        measurements={
            "required_maximum_cpi": requirement.maximum_characters_per_inch,
            "physical_scale_available": False,
        },
    )
    checks = GovernmentWarningChecks(
        presence=presence,
        wording=wording,
        heading_capitalization=capitalization,
        heading_boldness=heading_boldness,
        body_not_bold=body_not_bold,
        continuous_statement=continuity,
        separation=separation,
        legibility_contrast=contrast,
        type_size=type_size,
        characters_per_inch=characters_per_inch,
    )
    statuses = [getattr(checks, name).status for name in GovernmentWarningChecks.model_fields]
    if "mismatch" in statuses:
        overall_status = "mismatch"
    elif presence.status == "not_found":
        overall_status = "not_found"
    elif "review" in statuses or "not_found" in statuses:
        overall_status = "review"
    else:
        overall_status = "match"

    box = localized.bounding_box if localized else None
    return GovernmentWarningAnalysis(
        overall_status=overall_status,
        localized_text=localized.text if localized else None,
        source_lines=list(localized.source_lines) if localized else [],
        bounding_box=(
            WarningBoundingBox(
                left=box.left,
                top=box.top,
                width=box.width,
                height=box.height,
            )
            if box
            else None
        ),
        mean_ocr_confidence=localized.mean_confidence if localized else None,
        analysis_duration_ms=(perf_counter() - started) * 1_000,
        checks=checks,
    )


def _localize_warning(ocr_result: OcrResult) -> LocalizedWarning | None:
    regions = tuple(region for region in ocr_result.regions if region.text.strip())
    if regions:
        localized = _localize_structured(ocr_result, regions)
        if localized is not None:
            return localized
    return _localize_raw_text(ocr_result.text)


def _localize_structured(
    ocr_result: OcrResult, regions: tuple[TextRegion, ...]
) -> LocalizedWarning | None:
    lines = reconstruct_ocr_lines(ocr_result)
    panels: dict[int, list[OcrLine]] = {}
    for line in lines:
        panels.setdefault(line.panel_id, []).append(line)

    selected_lines: list[OcrLine] | None = None
    exact_heading_anchor = False
    distinctive_anchor = False
    for panel_lines in panels.values():
        panel_lines.sort(
            key=lambda line: (
                line.top if line.top is not None else 10**9,
                line.left if line.left is not None else 10**9,
            )
        )
        panel_tokens = [_tokens(line.text) for line in panel_lines]
        heading_line = next(
            (
                index
                for index, tokens in enumerate(panel_tokens)
                if _sequence_index(tokens, ["government", "warning"]) is not None
            ),
            None,
        )
        distinctive_line = next(
            (
                index
                for index, tokens in enumerate(panel_tokens)
                if _sequence_index(tokens, ["according", "to", "the", "surgeon", "general"])
                is not None
            ),
            None,
        )
        if heading_line is None and distinctive_line is None:
            continue
        start_line = heading_line if heading_line is not None else max(0, distinctive_line - 1)
        candidate_lines = _warning_lines_from(panel_lines, start_line)
        candidate_tokens = [token for line in candidate_lines for token in _tokens(line.text)]
        has_heading = _sequence_index(candidate_tokens, ["government", "warning"]) is not None
        has_distinctive = (
            _sequence_index(candidate_tokens, ["according", "to", "the", "surgeon", "general"])
            is not None
        )
        if selected_lines is None or (has_heading and has_distinctive):
            selected_lines = candidate_lines
            exact_heading_anchor = has_heading
            distinctive_anchor = has_distinctive
        if has_heading and has_distinctive:
            break

    if not selected_lines:
        return None

    selected = tuple(word for line in selected_lines for word in line.words)
    original_indexes = {id(region): index for index, region in enumerate(regions)}
    indexes = frozenset(
        original_indexes[id(region)] for region in selected if id(region) in original_indexes
    )
    source_lines = tuple(line.text for line in selected_lines)
    confidences = [region.confidence for region in selected if region.confidence is not None]
    boxes = [region.bounding_box for region in selected if region.bounding_box is not None]
    return LocalizedWarning(
        text=" ".join(region.text for region in selected),
        regions=selected,
        region_indexes=indexes,
        source_lines=source_lines,
        bounding_box=_union_boxes(boxes),
        mean_confidence=statistics.fmean(confidences) if confidences else None,
        exact_heading_anchor=exact_heading_anchor,
        distinctive_anchor=distinctive_anchor,
    )


def _warning_lines_from(lines: list[OcrLine], start: int) -> list[OcrLine]:
    selected: list[OcrLine] = []
    tokens: list[str] = []
    anchor = lines[start]
    heights = [
        line.approximate_line_height
        for line in lines[start:]
        if line.approximate_line_height is not None
    ]
    typical_height = statistics.median(heights) if heights else 20
    previous_bottom: int | None = None
    for line in lines[start : start + 40]:
        if line is not anchor and not _shares_warning_column(anchor, line):
            continue
        box = line.bounding_box
        if (
            selected
            and box is not None
            and previous_bottom is not None
            and box.top - previous_bottom > typical_height * 6
        ):
            break
        selected.append(line)
        tokens.extend(_tokens(line.text))
        if box is not None:
            previous_bottom = box.top + box.height
        ending = _sequence_index(tokens, ["health", "problems"])
        if ending is not None:
            break
        if len(tokens) >= 100:
            break
        if len(selected) >= 14:
            break
    return selected


def _shares_warning_column(anchor: OcrLine, candidate: OcrLine) -> bool:
    first = anchor.bounding_box
    second = candidate.bounding_box
    if first is None or second is None:
        return True
    overlap = max(
        0,
        min(first.left + first.width, second.left + second.width) - max(first.left, second.left),
    )
    minimum_width = min(first.width, second.width)
    first_center = first.left + first.width / 2
    second_center = second.left + second.width / 2
    return overlap >= minimum_width * 0.25 and abs(first_center - second_center) <= max(
        first.width, second.width
    )


def _localize_raw_text(raw_text: str) -> LocalizedWarning | None:
    lines = [" ".join(line.split()) for line in raw_text.splitlines() if line.strip()]
    joined = " ".join(lines)
    heading = re.search(r"\bgovernment\s+warning\b", joined, re.IGNORECASE)
    distinctive = re.search(r"\baccording\s+to\s+the\s+surgeon\s+general\b", joined, re.IGNORECASE)
    if heading is None and distinctive is None:
        return None
    start = heading.start() if heading else max(0, distinctive.start() - 30)
    tail = joined[start:]
    ending = re.search(r"\bhealth\s+problems\s*\.", tail, re.IGNORECASE)
    text = tail[: ending.end()] if ending else tail
    matching_lines = tuple(
        line for line in lines if line in text or any(part in text for part in line.split())
    )
    return LocalizedWarning(
        text=text,
        regions=(),
        region_indexes=frozenset(),
        source_lines=matching_lines,
        bounding_box=None,
        mean_confidence=None,
        exact_heading_anchor=heading is not None,
        distinctive_anchor=distinctive is not None,
    )


def _presence_check(localized: LocalizedWarning | None) -> WarningCheck:
    if localized is None:
        return WarningCheck(
            status="not_found",
            explanation="No reliable Government Warning statement was located in the OCR evidence.",
        )
    if localized.exact_heading_anchor and localized.distinctive_anchor:
        return WarningCheck(
            status="match",
            explanation=_sentence(
                "A likely Government Warning was located using its heading and",
                "distinctive wording.",
            ),
            evidence=list(localized.source_lines),
        )
    return WarningCheck(
        status="review",
        explanation=_sentence(
            "Possible Government Warning text was located, but the anchor",
            "evidence is incomplete.",
        ),
        evidence=list(localized.source_lines),
    )


def _wording_check(localized: LocalizedWarning | None) -> WarningCheck:
    if localized is None:
        return _not_found_check(
            "Required warning wording could not be checked because no warning was located."
        )
    observed = _normalize_warning_text(localized.text)
    expected = _normalize_warning_text(PRESCRIBED_GOVERNMENT_WARNING)
    evidence = [localized.text]
    if observed == expected:
        return WarningCheck(
            status="match",
            explanation=_sentence(
                "The extracted warning matches the prescribed wording after",
                "OCR-safe whitespace normalization.",
            ),
            evidence=evidence,
        )

    observed_tokens = WORD_PATTERN.findall(observed)
    expected_tokens = WORD_PATTERN.findall(expected)
    character_similarity = SequenceMatcher(None, observed, expected).ratio()
    token_matcher = SequenceMatcher(None, expected_tokens, observed_tokens)
    token_similarity = token_matcher.ratio()
    if _reviewable_wording_damage(localized, expected_tokens, observed_tokens, token_matcher):
        return WarningCheck(
            status="review",
            explanation=(
                "The warning appears substantially consistent with the prescribed wording, "
                "but OCR uncertainty requires manual review."
            ),
            evidence=evidence,
            measurements={
                "text_similarity": round(character_similarity, 3),
                "token_similarity": round(token_similarity, 3),
            },
        )

    return WarningCheck(
        status="mismatch",
        explanation=_sentence(
            "The extracted warning has missing, changed, reordered, or materially",
            "punctuated text.",
        ),
        evidence=evidence,
        measurements={
            "text_similarity": round(character_similarity, 3),
            "token_similarity": round(token_similarity, 3),
        },
    )


def _capitalization_check(localized: LocalizedWarning | None) -> WarningCheck:
    if localized is None:
        return _not_found_check(
            "Heading capitalization could not be checked because no warning was located."
        )
    match = re.match(r"\s*([^\s:]+)\s+([^\s:]+)", localized.text)
    if match is None:
        return WarningCheck(
            status="review",
            explanation="The warning heading was too incomplete to assess capitalization.",
            evidence=[localized.text],
        )
    observed = f"{match.group(1)} {match.group(2)}"
    if observed == GOVERNMENT_WARNING_HEADING:
        return WarningCheck(
            status="match",
            explanation="OCR preserves the heading as uppercase “GOVERNMENT WARNING.”",
            evidence=[observed],
        )
    if observed.casefold() == GOVERNMENT_WARNING_HEADING.casefold():
        return WarningCheck(
            status="mismatch",
            explanation=f"OCR represents the heading as “{observed},” not in all capital letters.",
            evidence=[observed],
        )
    return WarningCheck(
        status="review",
        explanation="OCR damage prevents a reliable capitalization determination for the heading.",
        evidence=[observed],
    )


def _visual_weight_checks(
    localized: LocalizedWarning | None, image_data: bytes
) -> tuple[WarningCheck, WarningCheck]:
    if localized is None:
        return (
            _not_found_check(
                "Heading boldness could not be assessed because no warning was located."
            ),
            _not_found_check("Body weight could not be assessed because no warning was located."),
        )
    if not localized.exact_heading_anchor:
        return _insufficient_weight_checks(
            "The heading anchor is incomplete, so heading/body visual weight cannot be aligned."
        )
    if len(localized.regions) < 10:
        return _insufficient_weight_checks(
            "Structured word boxes are insufficient for visual-weight analysis."
        )

    heading = localized.regions[:2]
    body = localized.regions[2:]
    try:
        with Image.open(BytesIO(image_data)) as source:
            image = source.convert("L")
            heading_metrics = _weight_metrics(image, heading)
            body_metrics = _weight_metrics(image, body)
    except (OSError, ValueError):
        return _insufficient_weight_checks("The warning crop could not be analyzed reliably.")
    if heading_metrics is None or body_metrics is None:
        return _insufficient_weight_checks(
            "The warning text is too small or indistinct for reliable relative-weight analysis."
        )

    heading_stroke, heading_density, heading_height = heading_metrics
    body_stroke, body_density, body_height = body_metrics
    ratio = heading_stroke / body_stroke if body_stroke else 0
    measurements = {
        "heading_stroke_index": round(heading_stroke, 3),
        "body_stroke_index": round(body_stroke, 3),
        "relative_stroke_ratio": round(ratio, 3),
        "heading_ink_density": round(heading_density, 3),
        "body_ink_density": round(body_density, 3),
        "median_heading_height_px": round(heading_height, 1),
        "median_body_height_px": round(body_height, 1),
    }
    if min(heading_height, body_height) < 9:
        return _insufficient_weight_checks(
            "The warning text is too small for defensible font-weight estimation.", measurements
        )
    if ratio >= 1.2:
        return (
            WarningCheck(
                status="match",
                explanation="The heading has substantially heavier strokes than the warning body.",
                measurements=measurements,
            ),
            WarningCheck(
                status="match",
                explanation=_sentence(
                    "The body is substantially lighter than the heading in this",
                    "warning region.",
                ),
                measurements=measurements,
            ),
        )
    if ratio < 0.85:
        return (
            WarningCheck(
                status="mismatch",
                explanation=_sentence(
                    "The heading appears lighter than the warning body, contrary",
                    "to the required emphasis.",
                ),
                measurements=measurements,
            ),
            WarningCheck(
                status="mismatch",
                explanation="The body appears heavier than the heading and may be bold.",
                measurements=measurements,
            ),
        )
    return _insufficient_weight_checks(
        _sentence(
            "Heading and body stroke measurements are too similar for a reliable",
            "bold/non-bold determination.",
        ),
        measurements,
    )


def _continuity_check(localized: LocalizedWarning | None) -> WarningCheck:
    if localized is None:
        return _not_found_check(
            "Statement continuity could not be checked because no warning was located."
        )
    normalized = _normalize_warning_text(localized.text)
    observed_tokens = WORD_PATTERN.findall(normalized)
    first_anchor = _approximate_sequence_index(observed_tokens, CLAUSE_ONE_ANCHOR)
    second_anchor = _approximate_sequence_index(observed_tokens, CLAUSE_TWO_ANCHOR)
    if first_anchor is None or second_anchor is None:
        return WarningCheck(
            status="mismatch",
            explanation=(
                "Substantial text from one or both prescribed warning clauses was not found."
            ),
            evidence=list(localized.source_lines),
        )
    if first_anchor > second_anchor:
        return WarningCheck(
            status="mismatch",
            explanation="The prescribed warning clauses appear out of order.",
            evidence=list(localized.source_lines),
        )
    first_marker = CLAUSE_ONE_MARKER.search(normalized)
    second_marker = CLAUSE_TWO_MARKER.search(normalized)
    if first_marker is None or second_marker is None:
        return WarningCheck(
            status="review",
            explanation=(
                "Both prescribed clauses occur in order, but OCR did not preserve both "
                "numbered markers reliably."
            ),
            evidence=list(localized.source_lines),
        )
    expected_tokens = WORD_PATTERN.findall(_normalize_warning_text(PRESCRIBED_GOVERNMENT_WARNING))
    token_changes = SequenceMatcher(None, expected_tokens, observed_tokens).get_opcodes()
    unrelated_insertions = _unrelated_inserted_token_indexes(
        expected_tokens, observed_tokens, token_changes
    )
    token_confidences = _localized_token_confidences(localized)
    confident_unrelated = [
        index
        for index in unrelated_insertions
        if index >= len(token_confidences)
        or token_confidences[index] is None
        or token_confidences[index] >= LOW_CONFIDENCE_DIFFERENCE
    ]
    if confident_unrelated:
        return WarningCheck(
            status="mismatch",
            explanation="Unrelated words appear to interrupt the two numbered warning portions.",
            evidence=list(localized.source_lines),
            measurements={"unexpected_word_count": len(confident_unrelated)},
        )
    if unrelated_insertions:
        return WarningCheck(
            status="review",
            explanation=(
                "Low-confidence OCR fragments occur between otherwise ordered warning clauses."
            ),
            evidence=list(localized.source_lines),
            measurements={"uncertain_word_count": len(unrelated_insertions)},
        )
    if not localized.regions:
        return WarningCheck(
            status="review",
            explanation=_sentence(
                "The clauses occur in order, but OCR geometry is unavailable to",
                "assess continuity.",
            ),
            evidence=list(localized.source_lines),
        )
    paragraphs_by_block: dict[tuple[int | None, int | None], set[int]] = {}
    for region in localized.regions:
        if region.paragraph_id is None:
            continue
        block = (region.page_id, region.block_id)
        paragraphs_by_block.setdefault(block, set()).add(region.paragraph_id)
    if any(len(paragraphs) > 1 for paragraphs in paragraphs_by_block.values()):
        return WarningCheck(
            status="review",
            explanation="The clauses occur in order but include an OCR paragraph break.",
            evidence=list(localized.source_lines),
        )
    block_ids = {
        (region.page_id, region.block_id)
        for region in localized.regions
        if region.block_id is not None
    }
    if len(block_ids) > 1:
        return WarningCheck(
            status="review",
            explanation="The clauses occur in order but span multiple OCR text blocks.",
            evidence=list(localized.source_lines),
            measurements={"ocr_block_count": len(block_ids)},
        )
    line_boxes: dict[tuple[int | None, ...], list[BoundingBox]] = {}
    for region in localized.regions:
        if region.bounding_box is None:
            continue
        key = (region.page_id, region.block_id, region.paragraph_id, region.line_id)
        line_boxes.setdefault(key, []).append(region.bounding_box)
    bounds = [_union_boxes(list(boxes)) for boxes in line_boxes.values()]
    present_bounds = sorted((box for box in bounds if box is not None), key=lambda box: box.top)
    if len(present_bounds) > 1:
        median_height = statistics.median(box.height for box in present_bounds)
        largest_gap = max(
            later.top - (earlier.top + earlier.height)
            for earlier, later in zip(present_bounds, present_bounds[1:], strict=False)
        )
        if largest_gap > median_height * 2.5:
            return WarningCheck(
                status="review",
                explanation="A large spatial gap inside the warning requires continuity review.",
                evidence=list(localized.source_lines),
                measurements={"largest_interline_gap_px": largest_gap},
            )
    return WarningCheck(
        status="match",
        explanation=_sentence(
            "Both numbered portions occur in sequence within spatially coherent",
            "OCR lines; normal line wrapping is allowed.",
        ),
        evidence=list(localized.source_lines),
        measurements={"ocr_line_count": len(localized.source_lines)},
    )


def _separation_check(
    localized: LocalizedWarning | None, all_regions: tuple[TextRegion, ...]
) -> WarningCheck:
    if localized is None:
        return _not_found_check("Separation could not be checked because no warning was located.")
    if localized.bounding_box is None or not localized.regions:
        return WarningCheck(
            status="review",
            explanation=_sentence(
                "OCR geometry is unavailable, so separation from surrounding",
                "information requires review.",
            ),
        )
    other_boxes = [
        region.bounding_box
        for index, region in enumerate(all_regions)
        if index not in localized.region_indexes and region.bounding_box is not None
    ]
    if not other_boxes:
        return WarningCheck(
            status="match",
            explanation="No other OCR text was detected adjacent to the localized warning block.",
            measurements={"nearest_other_text_px": None},
        )
    distance = min(_box_distance(localized.bounding_box, box) for box in other_boxes)
    heights = [
        region.bounding_box.height
        for region in localized.regions
        if region.bounding_box is not None
    ]
    median_height = statistics.median(heights)
    ratio = distance / median_height if median_height else 0
    measurements = {
        "nearest_other_text_px": round(distance, 1),
        "nearest_distance_in_text_heights": round(ratio, 2),
    }
    if ratio >= 1.5:
        return WarningCheck(
            status="match",
            explanation=_sentence(
                "OCR geometry shows substantial whitespace between the warning",
                "and other detected text.",
            ),
            measurements=measurements,
        )
    return WarningCheck(
        status="review",
        explanation=_sentence(
            "Detected surrounding text is close enough that separate-and-apart",
            "presentation needs review.",
        ),
        measurements=measurements,
    )


def _contrast_check(localized: LocalizedWarning | None, image_data: bytes) -> WarningCheck:
    if localized is None:
        return _not_found_check("Contrast could not be assessed because no warning was located.")
    if localized.bounding_box is None or len(localized.regions) < 8:
        return WarningCheck(
            status="review",
            explanation=_sentence(
                "Structured warning geometry is insufficient for a conservative",
                "contrast estimate.",
            ),
        )
    try:
        with Image.open(BytesIO(image_data)) as source:
            crop = source.convert("L").crop(_pil_box(localized.bounding_box))
            pixels = list(crop.get_flattened_data())
    except (OSError, ValueError):
        return WarningCheck(
            status="review",
            explanation="The warning crop could not be analyzed for contrast.",
        )
    if len(pixels) < 500:
        return WarningCheck(
            status="review",
            explanation="The warning crop is too small for a useful contrast estimate.",
        )
    threshold = _otsu_threshold(pixels)
    low = [value for value in pixels if value <= threshold]
    high = [value for value in pixels if value > threshold]
    if not low or not high:
        return WarningCheck(
            status="review",
            explanation="The warning crop lacks enough tonal separation for analysis.",
        )
    foreground, background = (low, high) if len(low) < len(high) else (high, low)
    contrast = abs(statistics.fmean(foreground) - statistics.fmean(background)) / 255
    background_std = statistics.pstdev(background)
    confidence = localized.mean_confidence
    measurements = {
        "normalized_luminance_separation": round(contrast, 3),
        "background_luminance_stddev": round(background_std, 2),
        "mean_ocr_confidence": round(confidence, 3) if confidence is not None else None,
    }
    if contrast < 0.15:
        return WarningCheck(
            status="mismatch",
            explanation=_sentence(
                "The localized text and background have very low measured",
                "luminance separation.",
            ),
            measurements=measurements,
        )
    if contrast >= 0.45 and background_std <= 15 and confidence is not None and confidence >= 0.65:
        return WarningCheck(
            status="match",
            explanation=_sentence(
                "The crop has strong local luminance separation and a stable",
                "background; final legibility remains a reviewer judgment.",
            ),
            measurements=measurements,
        )
    return WarningCheck(
        status="review",
        explanation=_sentence(
            "Contrast, background variation, or OCR quality is not strong enough",
            "for a confident automated conclusion.",
        ),
        measurements=measurements,
    )


def _normalize_warning_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.translate(str.maketrans({"’": "'", "‘": "'", "–": "-", "—": "-"}))
    normalized = " ".join(normalized.split())
    normalized = re.sub(r"\s+([,:;.])", r"\1", normalized)
    return normalized.casefold()


def _ocr_equivalent_word(observed: str, expected: str) -> bool:
    if observed == expected:
        return True
    return observed.translate(COMMON_OCR_CHARACTERS) == expected


def _reviewable_wording_damage(
    localized: LocalizedWarning,
    expected_tokens: list[str],
    observed_tokens: list[str],
    matcher: SequenceMatcher,
) -> bool:
    """Identify bounded OCR corruption without forgiving substantive omissions."""

    if observed_tokens == expected_tokens:
        # Token identity with punctuation damage is still uncertain rather than an exact match.
        return True
    if matcher.ratio() < MINIMUM_REVIEW_TOKEN_SIMILARITY:
        return False

    confidences = _localized_token_confidences(localized)
    changed_observed_indexes: set[int] = set()
    change_groups = 0
    has_unpaired_change = False
    all_replacements_look_like_ocr = True
    deleted_tokens: list[str] = []
    for (
        operation,
        expected_start,
        expected_end,
        observed_start,
        observed_end,
    ) in matcher.get_opcodes():
        if operation == "equal":
            continue
        change_groups += 1
        expected_change = expected_tokens[expected_start:expected_end]
        observed_change = observed_tokens[observed_start:observed_end]
        changed_observed_indexes.update(range(observed_start, observed_end))
        if max(len(expected_change), len(observed_change)) > 3:
            return False
        if operation != "replace" or len(expected_change) != len(observed_change):
            has_unpaired_change = True
            all_replacements_look_like_ocr = False
            if operation == "delete":
                deleted_tokens.extend(expected_change)
            continue
        for required, actual in zip(expected_change, observed_change, strict=True):
            if not _plausible_ocr_substitution(actual, required):
                all_replacements_look_like_ocr = False

    if change_groups == 0:
        return False
    expected_counts = Counter(expected_tokens)
    observed_counts = Counter(observed_tokens)
    if any(observed_counts[token] < expected_counts[token] for token in deleted_tokens):
        return False
    if all_replacements_look_like_ocr and not has_unpaired_change:
        return True

    low_confidence_change = any(
        index < len(confidences)
        and confidences[index] is not None
        and confidences[index] < LOW_CONFIDENCE_DIFFERENCE
        for index in changed_observed_indexes
    )
    return low_confidence_change


def _plausible_ocr_substitution(observed: str, expected: str) -> bool:
    if _ocr_equivalent_word(observed, expected):
        return True
    if expected == "1" and observed in {"3", "7", "l", "i"}:
        return True
    if abs(len(observed) - len(expected)) > 2:
        return False
    return SequenceMatcher(None, observed, expected).ratio() >= 0.75


def _localized_token_confidences(localized: LocalizedWarning) -> list[float | None]:
    return [region.confidence for region in localized.regions for _token in _tokens(region.text)]


def _approximate_sequence_index(tokens: list[str], phrase: tuple[str, ...]) -> int | None:
    exact = _sequence_index(tokens, list(phrase))
    if exact is not None:
        return exact
    for index in range(len(tokens) - len(phrase) + 1):
        window = tokens[index : index + len(phrase)]
        differences = [
            (observed, expected)
            for observed, expected in zip(window, phrase, strict=True)
            if observed != expected
        ]
        # One damaged anchor token still preserves enough neighboring prescribed text to
        # locate the clause. Wording independently decides whether that token is a
        # reviewable OCR error or a substantive mismatch.
        if len(differences) == 1:
            return index
    return None


def _unrelated_inserted_token_indexes(
    expected_tokens: list[str],
    observed_tokens: list[str],
    opcodes: list[tuple[str, int, int, int, int]],
) -> list[int]:
    indexes: list[int] = []
    expected_vocabulary = set(expected_tokens)
    for operation, _expected_start, _expected_end, observed_start, observed_end in opcodes:
        if operation != "insert":
            continue
        for index in range(observed_start, observed_end):
            token = observed_tokens[index]
            if token in expected_vocabulary:
                continue
            if any(
                _plausible_ocr_substitution(token, required) for required in expected_vocabulary
            ):
                continue
            indexes.append(index)
    return indexes


def _word_token(value: str) -> str:
    words = WORD_PATTERN.findall(value.casefold())
    return words[0] if words else ""


def _tokens(value: str) -> list[str]:
    return WORD_PATTERN.findall(value.casefold())


def _sequence_index(tokens: list[str], phrase: list[str], *, start: int = 0) -> int | None:
    for index in range(start, len(tokens) - len(phrase) + 1):
        if tokens[index : index + len(phrase)] == phrase:
            return index
    return None


def _structured_lines(regions: tuple[TextRegion, ...]) -> tuple[str, ...]:
    lines: dict[tuple[int | None, ...], list[str]] = {}
    for index, region in enumerate(regions):
        key = (region.page_id, region.block_id, region.paragraph_id, region.line_id)
        if all(value is None for value in key):
            key = (index,)
        lines.setdefault(key, []).append(region.text)
    return tuple(" ".join(words) for words in lines.values())


def _union_boxes(boxes: list[BoundingBox | None]) -> BoundingBox | None:
    present = [box for box in boxes if box is not None]
    if not present:
        return None
    left = min(box.left for box in present)
    top = min(box.top for box in present)
    right = max(box.left + box.width for box in present)
    bottom = max(box.top + box.height for box in present)
    return BoundingBox(left=left, top=top, width=right - left, height=bottom - top)


def _weight_metrics(
    image: Image.Image, regions: tuple[TextRegion, ...]
) -> tuple[float, float, float] | None:
    strokes: list[float] = []
    densities: list[float] = []
    heights: list[int] = []
    for region in regions:
        box = region.bounding_box
        if box is None or box.width < 3 or box.height < 3:
            continue
        crop = image.crop(_pil_box(box))
        pixels = list(crop.get_flattened_data())
        threshold = _otsu_threshold(pixels)
        dark_mask = [value <= threshold for value in pixels]
        dark_count = sum(dark_mask)
        light_count = len(dark_mask) - dark_count
        foreground = dark_mask if dark_count <= light_count else [not value for value in dark_mask]
        area = sum(foreground)
        density = area / len(foreground) if foreground else 0
        if density < 0.02 or density > 0.7:
            continue
        perimeter = _mask_perimeter(foreground, crop.width, crop.height)
        if perimeter <= 0:
            continue
        strokes.append(2 * area / perimeter)
        densities.append(density)
        heights.append(box.height)
    if len(strokes) < min(2, len(regions)):
        return None
    return (
        statistics.median(strokes),
        statistics.median(densities),
        statistics.median(heights),
    )


def _mask_perimeter(mask: list[bool], width: int, height: int) -> int:
    perimeter = 0
    for y in range(height):
        for x in range(width):
            if not mask[y * width + x]:
                continue
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nx, ny = x + dx, y + dy
                if nx < 0 or ny < 0 or nx >= width or ny >= height or not mask[ny * width + nx]:
                    perimeter += 1
    return perimeter


def _otsu_threshold(pixels: list[int]) -> int:
    histogram = [0] * 256
    for value in pixels:
        histogram[value] += 1
    total = len(pixels)
    weighted_total = sum(index * count for index, count in enumerate(histogram))
    background_weight = 0
    background_sum = 0
    best_variance = -1.0
    best_threshold = 127
    for threshold, count in enumerate(histogram):
        background_weight += count
        if background_weight == 0:
            continue
        foreground_weight = total - background_weight
        if foreground_weight == 0:
            break
        background_sum += threshold * count
        background_mean = background_sum / background_weight
        foreground_mean = (weighted_total - background_sum) / foreground_weight
        variance = background_weight * foreground_weight * (background_mean - foreground_mean) ** 2
        if variance > best_variance:
            best_variance = variance
            best_threshold = threshold
    return best_threshold


def _box_distance(left: BoundingBox, right: BoundingBox) -> float:
    horizontal = max(
        left.left - (right.left + right.width), right.left - (left.left + left.width), 0
    )
    vertical = max(left.top - (right.top + right.height), right.top - (left.top + left.height), 0)
    return math.hypot(horizontal, vertical)


def _pil_box(box: BoundingBox) -> tuple[int, int, int, int]:
    return box.left, box.top, box.left + box.width, box.top + box.height


def _not_found_check(explanation: str) -> WarningCheck:
    return WarningCheck(status="not_found", explanation=explanation)


def _sentence(*parts: str) -> str:
    return " ".join(parts)


def _insufficient_weight_checks(
    explanation: str, measurements: dict[str, str | float | int | bool | None] | None = None
) -> tuple[WarningCheck, WarningCheck]:
    shared = measurements or {}
    return (
        WarningCheck(status="review", explanation=explanation, measurements=shared),
        WarningCheck(status="review", explanation=explanation, measurements=shared),
    )
