import asyncio
from io import BytesIO

from PIL import Image

from app.models.verification import ApplicationData
from app.services.comparison import compare_application_data
from app.services.ocr import BoundingBox, OcrResult, TextRegion
from app.services.ocr_refinement import (
    MAX_REGIONAL_OCR_CALLS,
    crop_for_refinement,
    plan_regional_refinements,
    refine_ocr_candidates,
)
from app.services.structured_extraction import extract_candidates


def expected_application() -> ApplicationData:
    return ApplicationData(
        brand_name="Malt & Hop Brewery",
        class_type="India Pale Ale",
        abv=4,
        net_contents="500 mL",
        producer_name="Example Brewery",
        producer_address="Hyattsville, MD",
        imported_product=False,
    )


def word(
    text: str,
    *,
    left: int,
    top: int,
    width: int,
    height: int,
    line_id: int,
    word_id: int,
    confidence: float = 0.9,
) -> TextRegion:
    return TextRegion(
        text=text,
        bounding_box=BoundingBox(left=left, top=top, width=width, height=height),
        confidence=confidence,
        page_id=1,
        block_id=1,
        paragraph_id=1,
        line_id=line_id,
        word_id=word_id,
    )


def line(
    text: str,
    *,
    left: int,
    top: int,
    height: int,
    line_id: int,
    confidence: float = 0.9,
) -> list[TextRegion]:
    regions: list[TextRegion] = []
    x = left
    for word_id, token in enumerate(text.split(), 1):
        width = max(25, len(token) * 18)
        regions.append(
            word(
                token,
                left=x,
                top=top,
                width=width,
                height=height,
                line_id=line_id,
                word_id=word_id,
                confidence=confidence,
            )
        )
        x += width + 16
    return regions


def full_image_ocr() -> OcrResult:
    regions = [
        *line("Malt 6 Hop", left=100, top=200, height=90, line_id=1),
        *line("Brewery", left=100, top=300, height=90, line_id=2),
        *line("India bale Ak ©", left=100, top=500, height=75, line_id=3),
        *line("IPA SERIES #1", left=150, top=590, height=35, line_id=4),
        *line("decorative unreadable ribbon", left=220, top=760, height=55, line_id=5),
        *line("4% ALCOHOL BY VOLUME", left=250, top=910, height=35, line_id=6),
    ]
    return OcrResult(
        text="\n".join(
            (
                "Malt 6 Hop",
                "Brewery",
                "India bale Ak ©",
                "IPA SERIES #1",
                "decorative unreadable ribbon",
                "4% ALCOHOL BY VOLUME",
            )
        ),
        regions=tuple(regions),
        image_width=1600,
        image_height=1200,
        engine_name="full-test-ocr",
        duration_ms=25,
    )


def regional_ocr(text: str, *, confidence: float = 0.9) -> OcrResult:
    regions = line(text, left=10, top=10, height=40, line_id=1, confidence=confidence)
    return OcrResult(
        text=text,
        regions=tuple(regions),
        image_width=800,
        image_height=150,
        engine_name="regional-test-ocr",
        duration_ms=12,
    )


def png_bytes() -> bytes:
    output = BytesIO()
    Image.new("L", (1600, 1200), "white").save(output, format="PNG")
    return output.getvalue()


class QueueRegionalOcrService:
    def __init__(self, responses: list[OcrResult | Exception]) -> None:
        self.responses = responses
        self.region_calls: list[tuple[bytes, int]] = []

    async def extract(self, image: bytes, *, media_type: str) -> OcrResult:
        del image, media_type
        return full_image_ocr()

    async def extract_region(
        self,
        image: bytes,
        *,
        media_type: str,
        page_segmentation_mode: int,
    ) -> OcrResult:
        assert media_type == "image/png"
        self.region_calls.append((image, page_segmentation_mode))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def initial_state():
    ocr = full_image_ocr()
    candidates = extract_candidates(ocr)
    return ocr, candidates, compare_application_data(expected_application(), candidates)


def test_plans_only_uncertain_fields_and_caps_regional_calls():
    ocr, candidates, results = initial_state()

    plans = plan_regional_refinements(ocr, candidates=candidates, results=results)

    assert [plan.field for plan in plans] == ["net_contents", "brand_name", "class_type"]
    assert [plan.page_segmentation_mode for plan in plans] == [7, 6, 7]
    assert len(plans) == MAX_REGIONAL_OCR_CALLS
    assert all(plan.crop.width > 0 and plan.crop.height > 0 for plan in plans)
    assert all(plan.crop.left + plan.crop.width <= ocr.image_width for plan in plans)
    assert all(plan.crop.top + plan.crop.height <= ocr.image_height for plan in plans)
    assert plans[1].crop.left < 100 and plans[1].crop.top < 200
    assert plans[1].crop.top + plans[1].crop.height > 390
    assert plans[2].crop.top < 500


def test_refinement_recovers_only_image_derived_supported_values():
    ocr, candidates, results = initial_state()
    service = QueueRegionalOcrService(
        [
            regional_ocr("1 PINT 0.9 FL OZ (500 ML)"),
            regional_ocr("Malt @ Hop\nBrewery"),
            regional_ocr("India Pale Ale o®"),
        ]
    )

    outcome = asyncio.run(
        refine_ocr_candidates(
            ocr_service=service,
            preprocessed_image=png_bytes(),
            full_ocr=ocr,
            expected=expected_application(),
            candidates=candidates,
            results=results,
        )
    )

    assert outcome.invocation_count == 3
    assert [item.selected for item in outcome.evidence] == [True, True, True]
    assert outcome.results.net_contents.status == "match"
    assert outcome.results.brand_name.status == "match"
    assert outcome.results.class_type.status == "match"
    assert outcome.results.net_contents.extracted_raw == "1 PINT 0.9 FL OZ (500 ML)"
    assert outcome.results.class_type.extracted_raw == "India Pale Ale"
    assert outcome.evidence[2].refined_text == "India Pale Ale o®"
    assert [mode for _image, mode in service.region_calls] == [7, 6, 7]


def test_refinement_does_not_replace_review_with_unsupported_or_low_confidence_text():
    ocr, candidates, results = initial_state()
    service = QueueRegionalOcrService(
        [
            regional_ocr("decorative ribbon"),
            regional_ocr("Malt and Something Else", confidence=0.2),
            regional_ocr("Vodka"),
        ]
    )

    outcome = asyncio.run(
        refine_ocr_candidates(
            ocr_service=service,
            preprocessed_image=png_bytes(),
            full_ocr=ocr,
            expected=expected_application(),
            candidates=candidates,
            results=results,
        )
    )

    assert outcome.invocation_count == 3
    assert [item.selected for item in outcome.evidence] == [False, False, False]
    assert outcome.results == results
    assert outcome.candidates == candidates


def test_warning_region_cannot_trigger_candidate_refinement():
    ocr, candidates, results = initial_state()
    covering_box = BoundingBox(left=0, top=0, width=1600, height=700)

    plans = plan_regional_refinements(
        ocr,
        candidates=candidates,
        results=results,
        excluded_regions=(covering_box,),
    )

    assert [plan.field for plan in plans] == ["net_contents"]


def test_product_refinement_crop_stays_inside_product_panel():
    base = full_image_ocr()
    warning_words = [
        *line("GOVERNMENT WARNING:", left=1050, top=180, height=32, line_id=20),
        *line(
            "According to the Surgeon General",
            left=1050,
            top=240,
            height=25,
            line_id=21,
        ),
    ]
    ocr = OcrResult(
        text=base.text + "\nGOVERNMENT WARNING:\nAccording to the Surgeon General",
        regions=(*base.regions, *warning_words),
        image_width=1600,
        image_height=1200,
        engine_name=base.engine_name,
        duration_ms=base.duration_ms,
    )
    excluded = BoundingBox(left=1000, top=100, width=600, height=300)
    candidates = extract_candidates(ocr, excluded_regions=(excluded,))
    results = compare_application_data(expected_application(), candidates)

    plans = plan_regional_refinements(
        ocr,
        candidates=candidates,
        results=results,
        excluded_regions=(excluded,),
    )

    product_plans = [plan for plan in plans if plan.field in {"brand_name", "class_type"}]
    assert product_plans
    assert all(plan.crop.left + plan.crop.width < excluded.left for plan in product_plans)


def test_no_refinement_when_full_image_fields_are_strong():
    text_lines = (
        "Malt & Hop Brewery",
        "India Pale Ale",
        "4% ABV",
        "500 ML",
        "Brewed by Example Brewery",
        "Hyattsville, MD",
    )
    regions = [
        region
        for line_id, value in enumerate(text_lines, 1)
        for region in line(value, left=100, top=line_id * 100, height=40, line_id=line_id)
    ]
    ocr = OcrResult(
        text="\n".join(text_lines),
        regions=tuple(regions),
        image_width=1600,
        image_height=1200,
        engine_name="full-test-ocr",
        duration_ms=25,
    )
    candidates = extract_candidates(ocr)
    results = compare_application_data(expected_application(), candidates)

    plans = plan_regional_refinements(ocr, candidates=candidates, results=results)

    assert all(
        getattr(results, field).status == "match"
        for field in ("brand_name", "class_type", "abv", "net_contents")
    )
    assert plans == ()


def test_crop_is_clamped_and_prepared_as_grayscale_png():
    cropped = crop_for_refinement(
        png_bytes(),
        BoundingBox(left=1500, top=1100, width=100, height=100),
    )

    with Image.open(BytesIO(cropped)) as image:
        assert image.format == "PNG"
        assert image.mode == "L"
        assert image.size == (100, 100)
