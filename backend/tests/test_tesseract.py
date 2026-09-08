import asyncio
import shutil
from io import BytesIO

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.services.ocr import OcrUnavailableError
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
