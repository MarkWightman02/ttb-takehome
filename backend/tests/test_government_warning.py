import asyncio
import shutil
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.services.government_warning import analyze_government_warning
from app.services.government_warning_rules import (
    GOVERNMENT_WARNING_CLAUSE_ONE,
    GOVERNMENT_WARNING_CLAUSE_TWO,
    PRESCRIBED_GOVERNMENT_WARNING,
    physical_warning_requirement,
)
from app.services.ocr import BoundingBox, OcrResult, TextRegion

REGULAR_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
BOLD_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def blank_png(width: int = 2200, height: int = 600, color: int = 255) -> bytes:
    output = BytesIO()
    Image.new("L", (width, height), color).save(output, format="PNG")
    return output.getvalue()


def raw_analysis(text: str, volume_ml: float = 750):
    return analyze_government_warning(
        OcrResult(
            text=text,
            regions=(),
            image_width=2200,
            image_height=600,
            engine_name="test-ocr",
            duration_ms=1,
        ),
        preprocessed_image=blank_png(),
        container_volume_ml=volume_ml,
    )


@pytest.mark.parametrize(
    "text",
    [
        PRESCRIBED_GOVERNMENT_WARNING,
        PRESCRIBED_GOVERNMENT_WARNING.replace(" ", "  ").replace("(2)", "\n(2)"),
        PRESCRIBED_GOVERNMENT_WARNING.replace("WARNING:", "WARNING："),
    ],
)
def test_correct_warning_wording_accepts_ocr_safe_formatting(text: str):
    result = raw_analysis(text)
    assert result.checks.presence.status == "match"
    assert result.checks.wording.status == "match"


@pytest.mark.parametrize(
    "text",
    [
        PRESCRIBED_GOVERNMENT_WARNING.replace("health problems", "problems"),
        PRESCRIBED_GOVERNMENT_WARNING.replace("birth defects", "birth injuries"),
        PRESCRIBED_GOVERNMENT_WARNING.replace(
            GOVERNMENT_WARNING_CLAUSE_ONE,
            "(1) Drinking alcohol may cause harm.",
        ),
        PRESCRIBED_GOVERNMENT_WARNING.replace(f"{GOVERNMENT_WARNING_CLAUSE_ONE} ", ""),
        PRESCRIBED_GOVERNMENT_WARNING.replace(f" {GOVERNMENT_WARNING_CLAUSE_TWO}", ""),
        (f"GOVERNMENT WARNING: {GOVERNMENT_WARNING_CLAUSE_TWO} {GOVERNMENT_WARNING_CLAUSE_ONE}"),
    ],
)
def test_substantive_warning_wording_changes_are_mismatches(text: str):
    assert raw_analysis(text).checks.wording.status == "mismatch"


def test_likely_ocr_character_damage_requires_review():
    text = PRESCRIBED_GOVERNMENT_WARNING.replace("GOVERNMENT", "G0VERNMENT")
    result = raw_analysis(text)
    assert result.checks.presence.status == "review"
    assert result.checks.wording.status == "review"
    assert result.checks.heading_capitalization.status == "review"


def test_numbered_marker_ocr_damage_requires_review_instead_of_mismatch():
    text = PRESCRIBED_GOVERNMENT_WARNING.replace("(1)", "(3)", 1)
    result = analyze_government_warning(
        structured_result(text, confidence_overrides={"(3)": 0.35}),
        preprocessed_image=blank_png(),
        container_volume_ml=750,
    )

    assert result.checks.wording.status == "review"
    assert result.checks.continuous_statement.status == "review"
    assert result.overall_status == "review"
    assert "requires manual review" in result.checks.wording.explanation


def test_damaged_marker_punctuation_requires_review():
    text = PRESCRIBED_GOVERNMENT_WARNING.replace("(2)", "2)")
    result = raw_analysis(text)
    assert result.checks.wording.status == "review"
    assert result.checks.continuous_statement.status == "review"


def test_one_obvious_ocr_character_substitution_requires_review():
    text = PRESCRIBED_GOVERNMENT_WARNING.replace("beverages", "beveraqes", 1)
    assert raw_analysis(text).checks.wording.status == "review"


def test_several_low_confidence_substitutions_require_review():
    text = PRESCRIBED_GOVERNMENT_WARNING.replace("women", "wxxen").replace("machinery", "mxxhinery")
    result = analyze_government_warning(
        structured_result(
            text,
            confidence_overrides={"wxxen": 0.25, "mxxhinery,": 0.31},
        ),
        preprocessed_image=blank_png(),
        container_volume_ml=750,
    )

    assert result.checks.wording.status == "review"


def test_realistic_fragmented_ocr_warning_requires_review():
    text = (
        "GOVERNMENT WARNING: (3) According to the Surgeon General, women should not "
        "drink alcoholic beverages during pregnancy because of the risk of birth defects. "
        "(2) Consumption of alcoholic S impairs your bevera to ability drive a car or "
        "operate machinery, and may cause health problems"
    )
    result = analyze_government_warning(
        structured_result(text, confidence_overrides={"alcoholic": 0.20, "S": 0.62}),
        preprocessed_image=blank_png(),
        container_volume_ml=750,
    )

    assert result.checks.wording.status == "review"
    assert result.checks.continuous_statement.status == "review"
    assert result.overall_status == "review"


def test_confidently_missing_prescribed_phrase_remains_mismatch():
    text = PRESCRIBED_GOVERNMENT_WARNING.replace(
        "during pregnancy because of the risk of birth defects", ""
    )
    assert raw_analysis(text).checks.wording.status == "mismatch"


def test_missing_prescribed_word_stays_mismatch_despite_other_low_confidence_damage():
    text = PRESCRIBED_GOVERNMENT_WARNING.replace("health problems", "problems").replace(
        "women", "wxxen"
    )
    result = analyze_government_warning(
        structured_result(text, confidence_overrides={"wxxen": 0.2}),
        preprocessed_image=blank_png(),
        container_volume_ml=750,
    )
    assert result.checks.wording.status == "mismatch"


def test_warning_not_found_is_not_fabricated():
    result = raw_analysis("OLD TOM DISTILLERY\nKentucky Straight Bourbon Whiskey")
    assert result.overall_status == "not_found"
    assert result.localized_text is None
    assert result.checks.presence.status == "not_found"
    assert result.checks.wording.status == "not_found"


@pytest.mark.parametrize(
    ("heading", "expected_status"),
    [
        ("GOVERNMENT WARNING", "match"),
        ("Government Warning", "mismatch"),
        ("government warning", "mismatch"),
        ("G0VERNMENT WARNING", "review"),
    ],
)
def test_heading_capitalization_preserves_ocr_representation(heading: str, expected_status: str):
    text = PRESCRIBED_GOVERNMENT_WARNING.replace("GOVERNMENT WARNING", heading)
    assert raw_analysis(text).checks.heading_capitalization.status == expected_status


def structured_result(
    text: str = PRESCRIBED_GOVERNMENT_WARNING,
    *,
    line_length: int = 9,
    include_boxes: bool = True,
    unrelated_before: bool = False,
    paragraph_break: bool = False,
    block_break: bool = False,
    confidence_overrides: dict[str, float] | None = None,
) -> OcrResult:
    words = text.split()
    regions: list[TextRegion] = []
    if unrelated_before:
        regions.append(
            TextRegion(
                text="BRAND",
                bounding_box=BoundingBox(left=20, top=10, width=100, height=20),
                confidence=0.98,
                page_id=1,
                block_id=1,
                paragraph_id=1,
                line_id=1,
                word_id=1,
            )
        )
    for index, word in enumerate(words):
        line = index // line_length
        column = index % line_length
        regions.append(
            TextRegion(
                text=word,
                bounding_box=(
                    BoundingBox(
                        left=100 + column * 120,
                        top=100 + line * 38,
                        width=max(25, len(word) * 12),
                        height=24,
                    )
                    if include_boxes
                    else None
                ),
                confidence=(confidence_overrides or {}).get(word, 0.94),
                page_id=1,
                block_id=3 if block_break and index > len(words) // 2 else 2,
                paragraph_id=2 if paragraph_break and index > len(words) // 2 else 1,
                line_id=line + 1,
                word_id=column + 1,
            )
        )
    return OcrResult(
        text=text,
        regions=tuple(regions),
        image_width=2200,
        image_height=600,
        engine_name="test-ocr",
        duration_ms=1,
    )


def test_multiline_structured_warning_localizes_bounding_region_and_lines():
    ocr = structured_result(unrelated_before=True)
    result = analyze_government_warning(
        ocr, preprocessed_image=blank_png(), container_volume_ml=750
    )
    assert result.localized_text == PRESCRIBED_GOVERNMENT_WARNING
    assert len(result.source_lines) > 1
    assert result.bounding_box is not None
    assert result.bounding_box.left == 100
    assert result.bounding_box.top == 100
    assert result.mean_ocr_confidence == pytest.approx(0.94)
    assert result.checks.continuous_statement.status == "match"


def test_fragmented_or_incomplete_geometry_remains_reviewable():
    fragmented = PRESCRIBED_GOVERNMENT_WARNING.replace("GOVERNMENT", "GOVERN MENT")
    result = analyze_government_warning(
        structured_result(fragmented, include_boxes=False),
        preprocessed_image=blank_png(),
        container_volume_ml=750,
    )
    assert result.checks.presence.status == "review"
    assert result.bounding_box is None
    assert result.checks.separation.status == "review"
    assert result.checks.heading_boldness.status == "review"


def test_paragraph_ids_do_not_override_coherent_continuity_geometry():
    result = analyze_government_warning(
        structured_result(paragraph_break=True),
        preprocessed_image=blank_png(),
        container_volume_ml=750,
    )
    assert result.checks.continuous_statement.status == "match"


def test_ocr_block_fragmentation_alone_does_not_prevent_continuity_match():
    result = analyze_government_warning(
        structured_result(block_break=True),
        preprocessed_image=blank_png(),
        container_volume_ml=750,
    )
    assert result.checks.wording.status == "match"
    assert result.checks.continuous_statement.status == "match"


@pytest.mark.parametrize(
    "text",
    [
        PRESCRIBED_GOVERNMENT_WARNING.replace(f"{GOVERNMENT_WARNING_CLAUSE_ONE} ", ""),
        PRESCRIBED_GOVERNMENT_WARNING.replace(f" {GOVERNMENT_WARNING_CLAUSE_TWO}", ""),
    ],
)
def test_missing_numbered_clause_remains_continuity_mismatch(text: str):
    assert raw_analysis(text).checks.continuous_statement.status == "mismatch"


def test_reordered_clauses_remain_continuity_mismatch():
    text = f"GOVERNMENT WARNING: {GOVERNMENT_WARNING_CLAUSE_TWO} {GOVERNMENT_WARNING_CLAUSE_ONE}"
    assert raw_analysis(text).checks.continuous_statement.status == "mismatch"


def test_unrelated_line_interrupting_clauses_is_not_treated_as_continuous():
    interrupted = PRESCRIBED_GOVERNMENT_WARNING.replace(
        "(2) Consumption", "SPECIAL OFFER TODAY (2) Consumption"
    )
    result = analyze_government_warning(
        structured_result(interrupted),
        preprocessed_image=blank_png(),
        container_volume_ml=750,
    )
    assert result.checks.continuous_statement.status == "mismatch"
    assert result.checks.continuous_statement.measurements["unexpected_word_count"] == 3


def test_separation_uses_surrounding_whitespace_but_keeps_close_text_reviewable():
    isolated = analyze_government_warning(
        structured_result(),
        preprocessed_image=blank_png(),
        container_volume_ml=750,
    )
    assert isolated.checks.separation.status == "match"
    assert isolated.bounding_box is not None

    base = structured_result()
    box = isolated.bounding_box
    neighbor = TextRegion(
        text="CONTAINS SULFITES",
        bounding_box=BoundingBox(
            left=box.left + box.width + 4,
            top=box.top + box.height - 24,
            width=180,
            height=24,
        ),
        confidence=0.97,
        page_id=1,
        block_id=3,
        paragraph_id=1,
        line_id=1,
        word_id=1,
    )
    close = analyze_government_warning(
        OcrResult(
            text=base.text,
            regions=(*base.regions, neighbor),
            image_width=base.image_width,
            image_height=base.image_height,
            engine_name=base.engine_name,
            duration_ms=base.duration_ms,
        ),
        preprocessed_image=blank_png(),
        container_volume_ml=750,
    )
    assert close.checks.separation.status == "review"


@pytest.mark.parametrize(
    ("volume_ml", "minimum_mm", "maximum_cpi"),
    [
        (237, 1, 40),
        (237.1, 2, 25),
        (3000, 2, 25),
        (3000.1, 3, 12),
    ],
)
def test_physical_requirement_tiers_and_unsupported_scale_review(
    volume_ml: float, minimum_mm: int, maximum_cpi: int
):
    requirement = physical_warning_requirement(volume_ml)
    assert requirement.minimum_type_size_mm == minimum_mm
    assert requirement.maximum_characters_per_inch == maximum_cpi

    result = raw_analysis(PRESCRIBED_GOVERNMENT_WARNING, volume_ml)
    assert result.checks.type_size.status == "review"
    assert result.checks.type_size.measurements["required_minimum_mm"] == minimum_mm
    assert result.checks.characters_per_inch.status == "review"
    assert result.checks.characters_per_inch.measurements["required_maximum_cpi"] == maximum_cpi


def synthetic_warning(
    *,
    heading_bold: bool,
    body_bold: bool,
    foreground: int = 0,
    background: int = 255,
    font_size: int = 32,
    textured: bool = False,
    heading_font_size: int | None = None,
) -> tuple[OcrResult, bytes]:
    image = Image.new("L", (2200, 620), background)
    if textured:
        pixels = image.load()
        for y in range(image.height):
            for x in range(image.width):
                pixels[x, y] = max(0, min(255, background + ((x * 13 + y * 7) % 81) - 40))
    draw = ImageDraw.Draw(image)
    regular = ImageFont.truetype(str(REGULAR_FONT), font_size)
    bold = ImageFont.truetype(str(BOLD_FONT), font_size)
    heading_font = ImageFont.truetype(
        str(BOLD_FONT if heading_bold else REGULAR_FONT), heading_font_size or font_size
    )
    regions: list[TextRegion] = []
    x, y = 80, 80
    line_id = 1
    for index, word in enumerate(PRESCRIBED_GOVERNMENT_WARNING.split()):
        font = heading_font if index < 2 else (bold if body_bold else regular)
        bounds = draw.textbbox((x, y), word, font=font)
        width = bounds[2] - bounds[0]
        if x + width > 2050:
            x = 80
            y += font_size + 22
            line_id += 1
            bounds = draw.textbbox((x, y), word, font=font)
            width = bounds[2] - bounds[0]
        draw.text((x, y), word, fill=foreground, font=font)
        regions.append(
            TextRegion(
                text=word,
                bounding_box=BoundingBox(
                    left=bounds[0],
                    top=bounds[1],
                    width=bounds[2] - bounds[0],
                    height=bounds[3] - bounds[1],
                ),
                confidence=0.96,
                page_id=1,
                block_id=1,
                paragraph_id=1,
                line_id=line_id,
                word_id=index + 1,
            )
        )
        x += width + 14
    output = BytesIO()
    image.save(output, format="PNG")
    return (
        OcrResult(
            text=PRESCRIBED_GOVERNMENT_WARNING,
            regions=tuple(regions),
            image_width=image.width,
            image_height=image.height,
            engine_name="synthetic-ocr",
            duration_ms=1,
        ),
        output.getvalue(),
    )


@pytest.mark.skipif(
    not REGULAR_FONT.exists() or not BOLD_FONT.exists(), reason="DejaVu fonts unavailable"
)
def test_relative_visual_weight_distinguishes_bold_heading_from_body():
    ocr, image = synthetic_warning(heading_bold=True, body_bold=False)
    result = analyze_government_warning(ocr, preprocessed_image=image, container_volume_ml=750)
    assert result.checks.heading_boldness.status == "match"
    assert result.checks.body_not_bold.status == "match"


@pytest.mark.skipif(
    not REGULAR_FONT.exists() or not BOLD_FONT.exists(), reason="DejaVu fonts unavailable"
)
@pytest.mark.parametrize(
    ("heading_bold", "body_bold"), [(False, False), (True, True), (False, True)]
)
def test_similar_or_reversed_visual_weight_never_creates_false_match(
    heading_bold: bool, body_bold: bool
):
    ocr, image = synthetic_warning(heading_bold=heading_bold, body_bold=body_bold)
    result = analyze_government_warning(ocr, preprocessed_image=image, container_volume_ml=750)
    assert result.checks.heading_boldness.status in {"review", "mismatch"}
    assert result.checks.body_not_bold.status in {"review", "mismatch"}


@pytest.mark.skipif(
    not REGULAR_FONT.exists() or not BOLD_FONT.exists(), reason="DejaVu fonts unavailable"
)
def test_clear_contrast_matches_but_texture_requires_review():
    clear_ocr, clear_image = synthetic_warning(heading_bold=True, body_bold=False)
    clear = analyze_government_warning(
        clear_ocr, preprocessed_image=clear_image, container_volume_ml=750
    )
    assert clear.checks.legibility_contrast.status == "match"

    textured_ocr, textured_image = synthetic_warning(
        heading_bold=True, body_bold=False, textured=True
    )
    textured = analyze_government_warning(
        textured_ocr, preprocessed_image=textured_image, container_volume_ml=750
    )
    assert textured.checks.legibility_contrast.status == "review"


@pytest.mark.skipif(
    not REGULAR_FONT.exists() or not BOLD_FONT.exists(), reason="DejaVu fonts unavailable"
)
def test_light_text_on_dark_background_can_supply_contrast_evidence():
    ocr, image = synthetic_warning(heading_bold=True, body_bold=False, foreground=255, background=0)
    result = analyze_government_warning(ocr, preprocessed_image=image, container_volume_ml=750)
    assert result.checks.legibility_contrast.status == "match"


@pytest.mark.skipif(
    not REGULAR_FONT.exists() or not BOLD_FONT.exists(), reason="DejaVu fonts unavailable"
)
def test_low_contrast_and_tiny_text_do_not_receive_visual_matches():
    low_ocr, low_image = synthetic_warning(
        heading_bold=True, body_bold=False, foreground=140, background=160
    )
    low = analyze_government_warning(low_ocr, preprocessed_image=low_image, container_volume_ml=750)
    assert low.checks.legibility_contrast.status in {"review", "mismatch"}
    assert low.checks.heading_boldness.status == "review"
    assert low.checks.body_not_bold.status == "review"

    tiny_ocr, tiny_image = synthetic_warning(heading_bold=True, body_bold=False, font_size=8)
    tiny = analyze_government_warning(
        tiny_ocr, preprocessed_image=tiny_image, container_volume_ml=750
    )
    assert tiny.checks.heading_boldness.status == "review"


@pytest.mark.parametrize(
    "heading", ["GOVERNMENT : WARNING", "GOVERNMENT—WARNING", "GOVERNMENT WARNING："]
)
def test_heading_capitalization_ignores_only_punctuation(heading):
    text = PRESCRIBED_GOVERNMENT_WARNING.replace("GOVERNMENT WARNING:", heading)
    assert raw_analysis(text).checks.heading_capitalization.status == "match"


@pytest.mark.parametrize("marker", ["(3)", "(7)"])
def test_reliably_incorrect_clause_number_is_not_forgiven(marker):
    text = PRESCRIBED_GOVERNMENT_WARNING.replace("(1)", marker)
    result = analyze_government_warning(
        structured_result(text), preprocessed_image=blank_png(), container_volume_ml=750
    )
    assert result.checks.wording.status == "mismatch"


def test_ocr_joined_tokens_remain_review_not_match():
    text = PRESCRIBED_GOVERNMENT_WARNING.replace("drive a", "drivea")
    result = analyze_government_warning(
        structured_result(text, confidence_overrides={"drivea": 0.4}),
        preprocessed_image=blank_png(),
        container_volume_ml=750,
    )
    assert result.checks.wording.status == "review"


@pytest.mark.parametrize(
    "mode", ["vertical_gap", "different_column", "missing_box", "different_page"]
)
def test_complete_text_without_coherent_geometry_is_not_continuity_match(mode):
    ocr = structured_result()
    changed = []
    for region in ocr.regions:
        if region.line_id and region.line_id >= 5:
            box = region.bounding_box
            if mode == "vertical_gap":
                region = replace(region, bounding_box=replace(box, top=box.top + 250))
            elif mode == "different_column":
                region = replace(region, bounding_box=replace(box, left=box.left + 1400))
            elif mode == "missing_box":
                region = replace(region, bounding_box=None)
            else:
                region = replace(region, page_id=2)
        changed.append(region)
    # Test the continuity evidence itself; localization may legitimately return
    # only the first region when a clause is far away.
    from app.services.government_warning import _continuity_check, _localize_warning

    localized = _localize_warning(ocr)
    result = _continuity_check(replace(localized, regions=tuple(changed)))
    assert result.status == "review"


@pytest.mark.parametrize("heading_bold,body_bold", [(False, False), (True, True), (False, True)])
@pytest.mark.parametrize("heading_size", [48, 64])
def test_larger_heading_is_not_itself_boldness_evidence(heading_bold, body_bold, heading_size):
    ocr, image = synthetic_warning(
        heading_bold=heading_bold,
        body_bold=body_bold,
        heading_font_size=heading_size,
    )
    result = analyze_government_warning(ocr, preprocessed_image=image, container_volume_ml=750)
    assert result.checks.heading_boldness.status != "match"
    assert result.checks.body_not_bold.status != "match"


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("font_size", [24, 40, 56])
def test_clear_relative_weight_is_scale_and_polarity_aware(reverse, font_size):
    ocr, image = synthetic_warning(
        heading_bold=True,
        body_bold=False,
        font_size=font_size,
        foreground=255 if reverse else 0,
        background=0 if reverse else 255,
    )
    result = analyze_government_warning(ocr, preprocessed_image=image, container_volume_ml=750)
    assert result.checks.heading_boldness.status == "match"
    assert result.checks.body_not_bold.status == "match"
    assert result.checks.legibility_contrast.status == "match"


def test_dark_decoration_cannot_make_low_contrast_words_legible():
    ocr, data = synthetic_warning(
        heading_bold=True,
        body_bold=False,
        foreground=140,
        background=160,
    )
    with Image.open(BytesIO(data)) as source:
        image = source.convert("L")
    draw = ImageDraw.Draw(image)
    # High-contrast decoration in the warning rectangle, not the text strokes.
    draw.rectangle((80, 123, 2030, 131), fill=0)
    output = BytesIO()
    image.save(output, format="PNG")
    result = analyze_government_warning(
        ocr, preprocessed_image=output.getvalue(), container_volume_ml=750
    )
    assert result.checks.legibility_contrast.status != "match"


@pytest.mark.parametrize("reverse", [False, True])
def test_robust_contrast_fallback_rejects_noisy_whitespace(reverse):
    from app.services.government_warning import _localize_warning, _word_contrast_evidence

    ocr, data = synthetic_warning(
        heading_bold=True,
        body_bold=False,
        textured=True,
        foreground=255 if reverse else 0,
        background=35 if reverse else 220,
    )
    evidence = _word_contrast_evidence(_localize_warning(ocr), data)
    assert evidence["word_contrast_lower_quartile"] >= 0.55
    assert evidence["whitespace_spread_upper_quartile"] > 12
    result = analyze_government_warning(ocr, preprocessed_image=data, container_volume_ml=750)
    assert result.checks.legibility_contrast.status == "review"


def test_warning_in_unrelated_text_is_not_separate():
    from app.services.government_warning import _localize_warning, _separation_check

    ocr = structured_result()
    localized = _localize_warning(ocr)
    neighbor = replace(
        ocr.regions[0], text="SPECIAL OFFER", bounding_box=BoundingBox(130, 140, 120, 24)
    )
    result = _separation_check(localized, (*ocr.regions, neighbor))
    assert result.status == "review"


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract unavailable")
@pytest.mark.parametrize(
    "variant", ["clean", "reverse", "same_weight", "all_bold", "body_heavier", "low_contrast"]
)
def test_real_engine_warning_visual_controls(variant):
    from app.core.config import Settings
    from app.services.image_preprocessing import prepare_image
    from app.services.tesseract import TesseractOcrService

    _, source = synthetic_warning(
        heading_bold=variant not in {"same_weight", "body_heavier"},
        body_bold=variant in {"all_bold", "body_heavier"},
        foreground=255 if variant == "reverse" else 140 if variant == "low_contrast" else 0,
        background=0 if variant == "reverse" else 160 if variant == "low_contrast" else 255,
    )
    prepared = prepare_image(source, content_type="image/png", settings=Settings())
    service = TesseractOcrService(command="tesseract", language="eng", timeout_seconds=5)
    ocr = asyncio.run(service.extract(prepared.data, media_type="image/png"))
    result = analyze_government_warning(
        ocr,
        preprocessed_image=prepared.visual_evidence_data,
        container_volume_ml=750,
    )
    assert result.checks.wording.status == "match"
    assert result.checks.continuous_statement.status == "match"
    assert result.checks.type_size.status == "review"
    assert result.checks.characters_per_inch.status == "review"
    if variant in {"clean", "reverse"}:
        assert result.checks.heading_boldness.status == "match"
        assert result.checks.body_not_bold.status == "match"
        assert result.checks.legibility_contrast.status == "match"
    else:
        assert result.checks.heading_boldness.status != "match"
        assert result.checks.body_not_bold.status != "match"
    if variant == "low_contrast":
        assert result.checks.legibility_contrast.status != "match"
