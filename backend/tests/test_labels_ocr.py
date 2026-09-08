from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.main import create_app
from app.services.ocr import OcrProcessingError, OcrResult, OcrUnavailableError


def png_bytes(size: tuple[int, int] = (800, 400)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, "white").save(output, format="PNG")
    return output.getvalue()


class StubOcrService:
    def __init__(self, result: OcrResult | Exception) -> None:
        self.result = result
        self.received_image: bytes | None = None
        self.received_media_type: str | None = None

    async def extract(self, image: bytes, *, media_type: str) -> OcrResult:
        self.received_image = image
        self.received_media_type = media_type
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def successful_result() -> OcrResult:
    return OcrResult(
        text="OLD TOM DISTILLERY\n45% Alc./Vol.",
        regions=(),
        image_width=1600,
        image_height=800,
        engine_name="test-ocr",
        duration_ms=12.5,
        warnings=("Review faint text near the bottom of the label.",),
    )


def test_successful_image_upload_returns_raw_ocr_result(settings: Settings):
    service = StubOcrService(successful_result())
    with TestClient(create_app(settings, ocr_service=service)) as client:
        response = client.post(
            "/api/labels/ocr",
            files={"file": ("label.png", png_bytes(), "image/png")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["raw_text"] == "OLD TOM DISTILLERY\n45% Alc./Vol."
    assert payload["engine"] == "test-ocr"
    assert payload["ocr_duration_ms"] == 12.5
    assert payload["processing_duration_ms"] >= 0
    assert payload["image"] == {"width": 800, "height": 400, "format": "PNG"}
    assert payload["warnings"] == ["Review faint text near the bottom of the label."]
    assert service.received_media_type == "image/png"
    assert service.received_image is not None
    with Image.open(BytesIO(service.received_image)) as prepared:
        assert prepared.format == "PNG"
        assert prepared.mode == "L"
        assert prepared.size == (1600, 800)


def test_upload_rejects_unsupported_mime_type(settings: Settings):
    service = StubOcrService(successful_result())
    with TestClient(create_app(settings, ocr_service=service)) as client:
        response = client.post(
            "/api/labels/ocr",
            files={"file": ("label.gif", b"GIF89a", "image/gif")},
        )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_file_type"
    assert service.received_image is None


def test_upload_rejects_corrupt_image(settings: Settings):
    service = StubOcrService(successful_result())
    with TestClient(create_app(settings, ocr_service=service)) as client:
        response = client.post(
            "/api/labels/ocr",
            files={"file": ("label.png", b"not an image", "image/png")},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_image"
    assert service.received_image is None


def test_upload_rejects_oversized_file(settings: Settings):
    settings.max_upload_bytes = 16
    service = StubOcrService(successful_result())
    with TestClient(create_app(settings, ocr_service=service)) as client:
        response = client.post(
            "/api/labels/ocr",
            files={"file": ("label.png", png_bytes(), "image/png")},
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"
    assert service.received_image is None


def test_upload_requires_exactly_one_file(settings: Settings):
    service = StubOcrService(successful_result())
    with TestClient(create_app(settings, ocr_service=service)) as client:
        missing = client.post("/api/labels/ocr")
        multiple = client.post(
            "/api/labels/ocr",
            files=[
                ("file", ("front.png", png_bytes(), "image/png")),
                ("file", ("back.png", png_bytes(), "image/png")),
            ],
        )

    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "missing_file"
    assert multiple.status_code == 400
    assert multiple.json()["error"]["code"] == "multiple_files"


def test_ocr_processing_failure_returns_typed_error(settings: Settings):
    service = StubOcrService(OcrProcessingError("private engine details"))
    with TestClient(create_app(settings, ocr_service=service)) as client:
        response = client.post(
            "/api/labels/ocr",
            files={"file": ("label.png", png_bytes(), "image/png")},
        )

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "ocr_processing_failed",
            "message": "The image could not be processed by OCR. Try another image.",
        }
    }
    assert "private engine details" not in response.text


def test_missing_tesseract_returns_typed_unavailable_error(settings: Settings):
    service = StubOcrService(OcrUnavailableError("private command path"))
    with TestClient(create_app(settings, ocr_service=service)) as client:
        response = client.post(
            "/api/labels/ocr",
            files={"file": ("label.png", png_bytes(), "image/png")},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ocr_unavailable"
    assert "private command path" not in response.text
