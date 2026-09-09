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
        "producer_name": "Old Tom Distillery LLC",
        "producer_address": "Louisville, Kentucky",
        "imported_product": "false",
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
        "BOTTLED BY OLD TOM DISTILLERY LLC\nLOUISVILLE, KY\n" + PRESCRIBED_GOVERNMENT_WARNING
    )
    with TestClient(create_app(settings, ocr_service=service)) as client:
        response = verify(client)

    assert response.status_code == 200
    payload = response.json()
    assert service.calls == 1
    assert {
        result["status"] for name, result in payload["results"].items() if name != "country_origin"
    } == {"match"}
    assert payload["results"]["country_origin"]["status"] == "not_applicable"
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
    service = CountingOcrService(
        "OLD T0M DISTILLERY\nVodka\n40% ABV\n375 mL\nBottled by River Bend LLC\nNashville, TN"
    )
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
    assert {
        result["status"]
        for name, result in response.json()["results"].items()
        if name != "country_origin"
    } == {"not_found"}
    assert response.json()["results"]["country_origin"]["status"] == "not_applicable"
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


def test_warning_ocr_uncertainty_requires_review_without_mismatch_summary(settings: Settings):
    service = CountingOcrService(
        "OLD TOM DISTILLERY\nKentucky Straight Bourbon Whiskey\n45% Alc./Vol.\n750 mL\n"
        "BOTTLED BY OLD TOM DISTILLERY LLC\nLOUISVILLE, KY\n"
        + PRESCRIBED_GOVERNMENT_WARNING.replace("(1)", "(3)", 1)
    )
    with TestClient(create_app(settings, ocr_service=service)) as client:
        response = verify(client)

    assert response.status_code == 200
    payload = response.json()
    assert payload["government_warning"]["checks"]["wording"]["status"] == "review"
    assert payload["government_warning"]["overall_status"] == "review"
    assert payload["overall_summary"] == "One or more label checks require manual review."
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
                "producer_name": "Old Tom Distillery LLC",
                "producer_address": "Louisville, KY",
                "imported_product": "false",
            },
            files={"file": ("label.png", b"not an image", "image/png")},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_image"
    assert service.calls == 0


def test_unsupported_expected_volume_is_rejected_before_ocr(settings: Settings):
    service = CountingOcrService("unused")
    with TestClient(create_app(settings, ocr_service=service)) as client:
        response = verify(client, net_contents="1 gallon")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_net_contents"
    assert service.calls == 0


def test_us_pint_volume_is_accepted_and_compared_with_one_ocr_call(settings: Settings):
    service = CountingOcrService(
        "OLD TOM DISTILLERY\nBourbon Whiskey\n45% ABV\n1 PINT\n"
        "Bottled by Old Tom Distillery LLC\nLouisville, KY"
    )
    with TestClient(create_app(settings, ocr_service=service)) as client:
        response = verify(client, class_type="Bourbon Whiskey", net_contents="16 FL OZ")

    assert response.status_code == 200
    assert response.json()["results"]["net_contents"]["status"] == "match"
    assert service.calls == 1


def test_invalid_abv_is_a_typed_validation_error_before_ocr(settings: Settings):
    service = CountingOcrService("unused")
    with TestClient(create_app(settings, ocr_service=service)) as client:
        response = verify(client, abv="101")

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "The request contains invalid or missing values.",
        }
    }
    assert service.calls == 0


def test_missing_required_application_field_is_typed_before_ocr(settings: Settings):
    service = CountingOcrService("unused")
    with TestClient(create_app(settings, ocr_service=service)) as client:
        response = verify(client, producer_name="")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert service.calls == 0


def test_unexpected_multipart_field_is_ignored_without_changing_result(settings: Settings):
    service = CountingOcrService(
        "OLD TOM DISTILLERY\nBourbon Whiskey\n45% ABV\n750 mL\n"
        "Bottled by Old Tom Distillery LLC\nLouisville, KY"
    )
    with TestClient(create_app(settings, ocr_service=service)) as client:
        response = verify(client, class_type="Bourbon Whiskey", unrelated_input="ignored")

    assert response.status_code == 200
    assert service.calls == 1


def test_imported_country_match_and_origin_mismatch(settings: Settings):
    service = CountingOcrService(
        "OLD TOM DISTILLERY\nBourbon Whiskey\n45% ABV\n750 mL\n"
        "Imported by Old Tom Distillery LLC\nLouisville, KY\nProduct of France"
    )
    with TestClient(create_app(settings, ocr_service=service)) as client:
        matched = verify(
            client,
            class_type="Bourbon Whiskey",
            imported_product="true",
            country_origin="France",
        )
        mismatched = verify(
            client,
            class_type="Bourbon Whiskey",
            imported_product="true",
            country_origin="Italy",
        )

    assert matched.json()["results"]["country_origin"]["status"] == "match"
    assert mismatched.json()["results"]["country_origin"]["status"] == "mismatch"
    assert service.calls == 2


def test_imported_product_requires_country_before_ocr(settings: Settings):
    service = CountingOcrService("unused")
    with TestClient(create_app(settings, ocr_service=service)) as client:
        response = verify(client, imported_product="true", country_origin="")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "missing_country_origin"
    assert service.calls == 0


def test_imported_origin_not_found_is_a_field_result(settings: Settings):
    service = CountingOcrService(
        "OLD TOM DISTILLERY\nBourbon Whiskey\n45% ABV\n750 mL\n"
        "Imported by Old Tom Distillery LLC\nLouisville, KY"
    )
    with TestClient(create_app(settings, ocr_service=service)) as client:
        response = verify(
            client,
            class_type="Bourbon Whiskey",
            imported_product="true",
            country_origin="France",
        )

    assert response.status_code == 200
    assert response.json()["results"]["country_origin"]["status"] == "not_found"
    assert service.calls == 1


def test_producer_missing_is_a_field_result_and_ocr_runs_once(settings: Settings):
    service = CountingOcrService("OLD TOM DISTILLERY\nBourbon Whiskey\n45% ABV\n750 mL")
    with TestClient(create_app(settings, ocr_service=service)) as client:
        response = verify(client, class_type="Bourbon Whiskey")

    assert response.status_code == 200
    assert response.json()["results"]["producer_name"]["status"] == "not_found"
    assert response.json()["results"]["producer_address"]["status"] == "not_found"
    assert service.calls == 1
