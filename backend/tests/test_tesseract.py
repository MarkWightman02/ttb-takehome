import asyncio
import shutil
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.core.config import Settings
from app.models.verification import ApplicationData
from app.services.comparison import compare_application_data
from app.services.government_warning import analyze_government_warning
from app.services.government_warning_rules import PRESCRIBED_GOVERNMENT_WARNING
from app.services.image_preprocessing import prepare_image
from app.services.ocr import BoundingBox, OcrProcessingError, OcrUnavailableError
from app.services.structured_extraction import extract_candidates
from app.services.tesseract import TesseractOcrService, _parse_tsv
from evaluation.corpus import evaluation_cases, render_case


def test_tesseract_tsv_preserves_word_hierarchy_geometry_and_confidence():
    output = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\t"
        "height\tconf\ttext\n"
        "5\t1\t2\t3\t4\t1\t10\t20\t100\t30\t96.5\tGOVERNMENT\n"
        "5\t1\t2\t3\t4\t2\t120\t20\t90\t30\t91.0\tWARNING:\n"
    )

    text, regions = _parse_tsv(output)

    assert text == "GOVERNMENT WARNING:"
    assert regions[0].bounding_box is not None
    assert regions[0].bounding_box.left == 10
    assert regions[0].confidence == pytest.approx(0.965)
    assert (regions[0].page_id, regions[0].block_id) == (1, 2)
    assert (regions[0].paragraph_id, regions[0].line_id, regions[0].word_id) == (3, 4, 1)


def test_missing_tesseract_command_is_reported_as_unavailable():
    output = BytesIO()
    Image.new("L", (20, 20), "white").save(output, format="PNG")
    service = TesseractOcrService(
        command="definitely-not-a-real-tesseract-command",
        language="eng",
        timeout_seconds=1,
    )

    with pytest.raises(OcrUnavailableError):
        asyncio.run(service.extract(output.getvalue(), media_type="image/png"))


def test_tesseract_timeout_terminates_process_and_returns_processing_error(monkeypatch):
    output = BytesIO()
    Image.new("L", (20, 20), "white").save(output, format="PNG")

    class SlowProcess:
        returncode = None
        killed = False

        async def communicate(self, image: bytes):
            del image
            await asyncio.sleep(60)

        def kill(self):
            self.killed = True
            self.returncode = -9

        async def wait(self):
            return self.returncode

    process = SlowProcess()

    async def create_slow_process(*args, **kwargs):
        del args, kwargs
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_slow_process)
    service = TesseractOcrService(command="tesseract", language="eng", timeout_seconds=0.001)

    with pytest.raises(OcrProcessingError, match="timed out"):
        asyncio.run(service.extract(output.getvalue(), media_type="image/png"))

    assert process.killed is True


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract is not installed")
def test_real_tesseract_extracts_generated_label_text():
    image = Image.new("L", (1400, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.text(
        (60, 80),
        "OLD TOM DISTILLERY",
        fill="black",
        font=ImageFont.load_default(size=80),
    )
    output = BytesIO()
    image.save(output, format="PNG")
    service = TesseractOcrService(
        command=shutil.which("tesseract") or "tesseract",
        language="eng",
        timeout_seconds=5,
    )

    result = asyncio.run(service.extract(output.getvalue(), media_type="image/png"))

    assert "OLD TOM" in result.text.upper()
    assert result.engine_name == "tesseract-cli"
    assert result.duration_ms > 0


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract is not installed")
def test_real_verification_pipeline_extracts_generated_application_fields():
    image = Image.new("RGB", (1800, 1100), "white")
    draw = ImageDraw.Draw(image)
    draw.multiline_text(
        (80, 60),
        "OLD TOM DISTILLERY\nKentucky Straight Bourbon Whiskey\n45% ABV\n750 mL\n"
        "BOTTLED BY OLD TOM DISTILLERY LLC\nLOUISVILLE, KY\nPRODUCT OF FRANCE",
        fill="black",
        font=ImageFont.load_default(size=72),
        spacing=35,
    )
    output = BytesIO()
    image.save(output, format="PNG")
    prepared = prepare_image(
        output.getvalue(), content_type="image/png", settings=Settings(environment="test")
    )
    service = TesseractOcrService(
        command=shutil.which("tesseract") or "tesseract",
        language="eng",
        timeout_seconds=5,
    )

    ocr_result = asyncio.run(service.extract(prepared.data, media_type="image/png"))
    candidates = extract_candidates(ocr_result)
    results = compare_application_data(
        ApplicationData(
            brand_name="Old Tom Distillery",
            class_type="Kentucky Straight Bourbon Whiskey",
            abv=45,
            net_contents="750 mL",
            producer_name="Old Tom Distillery LLC",
            producer_address="Louisville, Kentucky",
            imported_product=True,
            country_origin="France",
        ),
        candidates,
    )

    assert "OLD TOM DISTILLERY" in ocr_result.text.upper()
    assert [candidate.normalized_percent for candidate in candidates.abv] == [45]
    assert [candidate.normalized_ml for candidate in candidates.net_contents] == [750]
    assert results.brand_name.status == "match"
    assert results.class_type.status == "match"
    assert results.abv.status == "match"
    assert results.net_contents.status == "match"
    assert results.producer_name.status == "match"
    assert results.producer_address.status == "match"
    assert results.country_origin.status == "match"


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract is not installed")
def test_real_tesseract_localizes_generated_government_warning():
    regular_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    bold_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    if not Path(regular_path).exists() or not Path(bold_path).exists():
        pytest.skip("DejaVu fonts are unavailable")
    image = Image.new("RGB", (2400, 1450), "white")
    draw = ImageDraw.Draw(image)
    title = ImageFont.truetype(bold_path, 72)
    body = ImageFont.truetype(regular_path, 38)
    heading = ImageFont.truetype(bold_path, 38)
    draw.multiline_text(
        (100, 70),
        "OLD TOM DISTILLERY\nKentucky Straight Bourbon Whiskey\n45% ABV\n750 mL",
        fill="black",
        font=title,
        spacing=25,
    )
    warning_y = 620
    draw.text((100, warning_y), "GOVERNMENT WARNING:", fill="black", font=heading)
    warning_lines = [
        "(1) According to the Surgeon General, women should not drink alcoholic beverages",
        "during pregnancy because of the risk of birth defects.",
        "(2) Consumption of alcoholic beverages impairs your ability to drive a car or",
        "operate machinery, and may cause health problems.",
    ]
    for line_number, line in enumerate(warning_lines, 1):
        draw.text(
            (100, warning_y + line_number * 65),
            line,
            fill="black",
            font=body,
        )
    output = BytesIO()
    image.save(output, format="PNG")
    prepared = prepare_image(
        output.getvalue(), content_type="image/png", settings=Settings(environment="test")
    )
    service = TesseractOcrService(
        command=shutil.which("tesseract") or "tesseract",
        language="eng",
        timeout_seconds=5,
    )

    ocr_result = asyncio.run(service.extract(prepared.data, media_type="image/png"))
    warning = analyze_government_warning(
        ocr_result,
        preprocessed_image=prepared.data,
        container_volume_ml=750,
    )

    assert len(ocr_result.regions) > 20
    assert warning.localized_text is not None
    assert "GOVERNMENT WARNING" in warning.localized_text.upper()
    assert warning.checks.presence.status == "match"
    assert warning.checks.wording.status in {"match", "review"}
    assert warning.checks.heading_capitalization.status == "match"
    assert warning.bounding_box is not None
    assert PRESCRIBED_GOVERNMENT_WARNING.startswith("GOVERNMENT WARNING:")


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract is not installed")
def test_real_tesseract_extracts_two_panel_label_without_warning_contamination():
    case = next(
        case for case in evaluation_cases() if case.name == "two_panel_product_left_warning_right"
    )
    rendered = render_case(case)
    prepared = prepare_image(
        rendered.data,
        content_type=rendered.media_type,
        settings=Settings(environment="test"),
    )
    service = TesseractOcrService(
        command=shutil.which("tesseract") or "tesseract",
        language="eng",
        timeout_seconds=5,
    )

    ocr_result = asyncio.run(service.extract(prepared.data, media_type="image/png"))
    warning = analyze_government_warning(
        ocr_result,
        preprocessed_image=prepared.visual_evidence_data,
        container_volume_ml=200,
    )
    assert warning.bounding_box is not None
    excluded = BoundingBox(
        left=warning.bounding_box.left,
        top=warning.bounding_box.top,
        width=warning.bounding_box.width,
        height=warning.bounding_box.height,
    )
    candidates = extract_candidates(ocr_result, excluded_regions=(excluded,))
    results = compare_application_data(case.application, candidates)

    assert "12345 IMPORTS IMPORTED BY: 12345 IMPORTS" in ocr_result.text
    assert [candidate.raw_value for candidate in candidates.brand_name] == ["12345 IMPORTS"]
    assert [candidate.raw_value for candidate in candidates.class_type] == [
        "RUM WITH COCONUT LIQUEUR"
    ]
    assert [candidate.normalized_percent for candidate in candidates.abv] == [18]
    assert [candidate.raw_value for candidate in candidates.net_contents] == ["200 ML"]
    assert [candidate.raw_value for candidate in candidates.producer_name] == ["12345 IMPORTS"]
    assert [candidate.raw_value for candidate in candidates.producer_address] == ["MIAMI, FL"]
    assert [candidate.raw_value for candidate in candidates.country_origin] == ["CANADA"]
    assert {getattr(results, field).status for field in type(results).model_fields} == {"match"}
    assert all(
        "surgeon" not in candidate.raw_value.casefold()
        and "ability to drive" not in candidate.raw_value.casefold()
        for field in (
            candidates.brand_name,
            candidates.class_type,
            candidates.producer_name,
            candidates.producer_address,
            candidates.country_origin,
        )
        for candidate in field
    )
