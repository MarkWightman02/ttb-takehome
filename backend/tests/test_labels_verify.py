from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.main import create_app
from app.services.government_warning_rules import PRESCRIBED_GOVERNMENT_WARNING
from app.services.ocr import OcrProcessingError, OcrResult


def png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (800, 400), "white").save(output, format="PNG")
    return output.getvalue()


class CountingOcrService:
    def __init__(self, text: str | Exception) -> None:
        self.text = text
        self.calls = 0

    async def extract(self, image: bytes, *, media_type: str) -> OcrResult:
        self.calls += 1
        if isinstance(self.text, Exception):
            raise self.text
        return OcrResult(
            text=self.text,
            regions=(),
            image_width=1600,
            image_height=800,
            engine_name="test-ocr",
            duration_ms=10,
        )


def verify(client: TestClient, **overrides: str):
    data = {
        "brand_name": "Old Tom Distillery",
        "class_type": "Kentucky Straight Bourbon Whiskey",
        "abv": "45",
        "net_contents": "750 mL",
    }
    data.update(overrides)
    return client.post(
        "/api/labels/verify",
        data=data,
        files={"file": ("label.png", png_bytes(), "image/png")},
    )


def test_all_fields_match_and_ocr_runs_exactly_once(settings: Settings):
    service = CountingOcrService(
        "OLD TOM DISTILLERY\nKentucky Straight Bourbon Whiskey\n45% Alc./Vol.\n750 mL\n"
        + PRESCRIBED_GOVERNMENT_WARNING
    )
    with TestClient(create_app(settings, ocr_service=service)) as client:
        response = verify(client)

    assert response.status_code == 200
    payload = response.json()
    assert service.calls == 1
    assert {result["status"] for result in payload["results"].values()} == {"match"}
    assert payload["overall_summary"] == (
        "All automated text checks matched; some visual requirements still require "
        "reviewer confirmation."
    )
    assert payload["raw_text"].startswith("OLD TOM")
    assert payload["engine"] == "test-ocr"
    assert payload["total_verification_duration_ms"] >= payload["ocr_duration_ms"]
    warning = payload["government_warning"]
    assert warning["checks"]["presence"]["status"] == "match"
    assert warning["checks"]["wording"]["status"] == "match"
    assert warning["checks"]["heading_capitalization"]["status"] == "match"
    assert warning["checks"]["heading_boldness"]["status"] == "review"
    assert warning["checks"]["type_size"]["measurements"]["required_minimum_mm"] == 2


def test_mixed_results_and_candidate_evidence(settings: Settings):
    service = CountingOcrService("OLD T0M DISTILLERY\nVodka\n40% ABV\n375 mL")
    with TestClient(create_app(settings, ocr_service=service)) as client:
        payload = verify(client).json()

    assert payload["results"]["brand_name"]["status"] == "review"
    assert payload["results"]["class_type"]["status"] == "mismatch"
    assert payload["results"]["abv"]["status"] == "mismatch"
    assert payload["results"]["net_contents"]["status"] == "mismatch"
    assert payload["candidates"]["abv"][0]["source_line"] == "40% ABV"


def test_missing_extraction_is_field_level_not_http_error(settings: Settings):
    service = CountingOcrService("")
    with TestClient(create_app(settings, ocr_service=service)) as client:
        response = verify(client)

    assert response.status_code == 200
    assert {result["status"] for result in response.json()["results"].values()} == {"not_found"}
    assert response.json()["government_warning"]["overall_status"] == "not_found"


def test_warning_text_mismatch_is_a_typed_result(settings: Settings):
    service = CountingOcrService(
        "OLD TOM DISTILLERY\nBourbon Whiskey\n45% ABV\n750 mL\n"
        + PRESCRIBED_GOVERNMENT_WARNING.replace("health problems", "health benefits")
    )
    with TestClient(create_app(settings, ocr_service=service)) as client:
        response = verify(client, class_type="Bourbon Whiskey")

    assert response.status_code == 200
    warning = response.json()["government_warning"]
    assert warning["checks"]["wording"]["status"] == "mismatch"
    assert warning["overall_status"] == "mismatch"
    assert service.calls == 1


def test_warning_capitalization_mismatch_is_separate_from_wording(settings: Settings):
    service = CountingOcrService(
        "OLD TOM DISTILLERY\nBourbon Whiskey\n45% ABV\n750 mL\n"
        + PRESCRIBED_GOVERNMENT_WARNING.replace("GOVERNMENT WARNING", "Government Warning")
    )
    with TestClient(create_app(settings, ocr_service=service)) as client:
        response = verify(client, class_type="Bourbon Whiskey")

    warning = response.json()["government_warning"]
    assert warning["checks"]["wording"]["status"] == "match"
    assert warning["checks"]["heading_capitalization"]["status"] == "mismatch"


def test_ocr_error_keeps_existing_typed_semantics(settings: Settings):
    service = CountingOcrService(OcrProcessingError("private detail"))
    with TestClient(create_app(settings, ocr_service=service)) as client:
        response = verify(client)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "ocr_processing_failed"
    assert service.calls == 1


def test_upload_validation_happens_before_ocr(settings: Settings):
    service = CountingOcrService("unused")
    with TestClient(create_app(settings, ocr_service=service)) as client:
        response = client.post(
            "/api/labels/verify",
            data={
                "brand_name": "Old Tom",
                "class_type": "Bourbon Whiskey",
                "abv": "45",
                "net_contents": "750 mL",
            },
            files={"file": ("label.png", b"not an image", "image/png")},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_image"
    assert service.calls == 0


def test_invalid_expected_metric_volume_is_rejected_before_ocr(settings: Settings):
    service = CountingOcrService("unused")
    with TestClient(create_app(settings, ocr_service=service)) as client:
        response = verify(client, net_contents="25 fl oz")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_net_contents"
    assert service.calls == 0
