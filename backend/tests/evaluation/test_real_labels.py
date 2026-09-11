import json
from io import BytesIO

import pytest
from PIL import Image

from evaluation.real_labels import discover_real_label_cases


def image_bytes(image_format: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", (20, 20), "white").save(output, format=image_format)
    return output.getvalue()


def application_data() -> dict[str, object]:
    return {
        "brand_name": "Example",
        "class_type": "Gin",
        "abv": 40,
        "net_contents": "750 mL",
        "producer_name": "Example Distillery",
        "producer_address": "Portland, OR",
        "imported": False,
        "country_of_origin": None,
    }


@pytest.mark.parametrize(
    ("extension", "image_format"), [(".jpg", "JPEG"), (".png", "PNG"), (".webp", "WEBP")]
)
def test_discovers_supported_real_label_pairs(tmp_path, extension: str, image_format: str):
    image = tmp_path / f"sample{extension}"
    image.write_bytes(image_bytes(image_format))
    image.with_suffix(".json").write_text(json.dumps(application_data()), encoding="utf-8")

    cases = discover_real_label_cases(tmp_path)

    assert len(cases) == 1
    assert cases[0].image_path == image
    assert cases[0].application.brand_name == "Example"


def test_supports_existing_brand_and_import_metadata_aliases(tmp_path):
    image = tmp_path / "sample.jpg"
    image.write_bytes(image_bytes("JPEG"))
    metadata = application_data()
    metadata["brand"] = metadata.pop("brand_name")
    image.with_suffix(".json").write_text(json.dumps(metadata), encoding="utf-8")

    case = discover_real_label_cases(tmp_path)[0]

    assert case.application.brand_name == "Example"
    assert case.application.imported_product is False


def test_image_without_matching_json_is_skipped_not_raised(tmp_path):
    # Mirrors examples/: the T01-T20 synthetic fixtures share this directory
    # with the real fixtures but use prefix-based metadata (T01.json), not a
    # same-stem file, and must not break real-label-only discovery.
    (tmp_path / "orphan.jpg").write_bytes(image_bytes("JPEG"))
    matched = tmp_path / "sample.jpg"
    matched.write_bytes(image_bytes("JPEG"))
    matched.with_suffix(".json").write_text(json.dumps(application_data()), encoding="utf-8")

    cases = discover_real_label_cases(tmp_path)

    assert len(cases) == 1
    assert cases[0].image_path == matched


def test_no_matching_pairs_raises(tmp_path):
    (tmp_path / "orphan.jpg").write_bytes(image_bytes("JPEG"))

    with pytest.raises(ValueError, match="No real-label image/JSON pairs"):
        discover_real_label_cases(tmp_path)
