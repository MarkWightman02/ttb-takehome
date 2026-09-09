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
                confidence=0.94,
                page_id=1,
                block_id=2,
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


def test_paragraph_break_requires_continuity_review():
    result = analyze_government_warning(
        structured_result(paragraph_break=True),
        preprocessed_image=blank_png(),
        container_volume_ml=750,
    )
    assert result.checks.continuous_statement.status == "review"


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
    regions: list[TextRegion] = []
    x, y = 80, 80
    line_id = 1
    for index, word in enumerate(PRESCRIBED_GOVERNMENT_WARNING.split()):
        font = bold if (index < 2 and heading_bold) or (index >= 2 and body_bold) else regular
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

    tiny_ocr, tiny_image = synthetic_warning(heading_bold=True, body_bold=False, font_size=8)
    tiny = analyze_government_warning(
        tiny_ocr, preprocessed_image=tiny_image, container_volume_ml=750
    )
    assert tiny.checks.heading_boldness.status == "review"
