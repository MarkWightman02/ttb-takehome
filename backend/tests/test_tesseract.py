import asyncio
import shutil
from io import BytesIO

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.core.config import Settings
from app.models.verification import ApplicationData
from app.services.comparison import compare_application_data
from app.services.image_preprocessing import prepare_image
from app.services.ocr import OcrUnavailableError
from app.services.structured_extraction import extract_candidates
from app.services.tesseract import TesseractOcrService


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
    image = Image.new("RGB", (1800, 750), "white")
    draw = ImageDraw.Draw(image)
    draw.multiline_text(
        (80, 60),
        "OLD TOM DISTILLERY\nKentucky Straight Bourbon Whiskey\n45% ABV\n750 mL",
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
    candidates = extract_candidates(ocr_result.text)
    results = compare_application_data(
        ApplicationData(
            brand_name="Old Tom Distillery",
            class_type="Kentucky Straight Bourbon Whiskey",
            abv=45,
            net_contents="750 mL",
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
