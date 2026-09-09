from collections.abc import Iterable
from io import BytesIO

from PIL import Image

from app.models.verification import ApplicationData
from app.services.comparison import compare_application_data
from app.services.government_warning import analyze_government_warning
from app.services.ocr import BoundingBox, OcrResult, TextRegion
from app.services.spatial_layout import reconstruct_ocr_lines
from app.services.structured_extraction import extract_candidates


def word(
    text: str,
    left: int,
    top: int,
    width: int,
    height: int,
    *,
    line_id: int,
    word_id: int,
) -> TextRegion:
    return TextRegion(
        text=text,
        bounding_box=BoundingBox(left=left, top=top, width=width, height=height),
        confidence=0.95,
        page_id=1,
        block_id=1,
        paragraph_id=1,
        line_id=line_id,
        word_id=word_id,
    )


def row(line_id: int, top: int, entries: Iterable[tuple[str, int, int, int]]) -> list[TextRegion]:
    return [
        word(text, left, top, width, height, line_id=line_id, word_id=index)
        for index, (text, left, width, height) in enumerate(entries, 1)
    ]


def ocr_result(regions: list[TextRegion], raw_text: str = "flattened OCR evidence") -> OcrResult:
    return OcrResult(
        text=raw_text,
        regions=tuple(regions),
        image_width=2600,
        image_height=1500,
        engine_name="test-tsv",
        duration_ms=10,
    )


def representative_regions(*, product_on_left: bool = True) -> list[TextRegion]:
    product_x, warning_x = (120, 1370) if product_on_left else (1370, 120)
    regions: list[TextRegion] = []
    regions += row(
        1,
        100,
        [
            ("12345", product_x, 150, 56),
            ("IMPORTS", product_x + 175, 250, 56),
            ("PRODUCED", warning_x, 200, 30),
            ("IN", warning_x + 220, 40, 30),
            ("CANADA", warning_x + 280, 170, 30),
        ],
    )
    regions += row(
        2,
        180,
        [
            ("IMPORTED", warning_x, 190, 30),
            ("BY:", warning_x + 210, 60, 30),
            ("12345", warning_x + 290, 120, 30),
            ("IMPORTS", warning_x + 430, 180, 30),
        ],
    )
    regions += row(
        3,
        250,
        [("MIAMI,", warning_x, 140, 30), ("FL", warning_x + 160, 45, 30)],
    )
    regions += row(
        4,
        400,
        [
            ("GOVERNMENT", warning_x, 280, 30),
            ("WARNING:", warning_x + 300, 210, 30),
        ],
    )
    regions += row(
        5,
        480,
        [
            ("RUM", product_x, 120, 44),
            ("WITH", product_x + 140, 140, 44),
            ("(1)", warning_x, 45, 28),
            ("According", warning_x + 60, 160, 28),
            ("to", warning_x + 235, 35, 28),
            ("the", warning_x + 285, 55, 28),
            ("Surgeon", warning_x + 355, 130, 28),
            ("General,", warning_x + 500, 140, 28),
        ],
    )
    regions += row(
        6,
        545,
        [
            ("COCONUT", product_x, 250, 44),
            ("LIQUEUR", product_x + 270, 225, 44),
            ("women", warning_x, 100, 28),
            ("should", warning_x + 115, 110, 28),
            ("not", warning_x + 240, 55, 28),
            ("drink", warning_x + 310, 85, 28),
            ("alcoholic", warning_x + 410, 145, 28),
            ("beverages", warning_x + 570, 170, 28),
        ],
    )
    regions += row(
        7,
        610,
        [
            ("during", warning_x, 105, 28),
            ("pregnancy", warning_x + 120, 175, 28),
            ("because", warning_x + 310, 140, 28),
            ("of", warning_x + 465, 35, 28),
            ("the", warning_x + 515, 55, 28),
            ("risk", warning_x + 585, 60, 28),
            ("of", warning_x + 660, 35, 28),
            ("birth", warning_x + 710, 75, 28),
            ("defects.", warning_x + 800, 130, 28),
        ],
    )
    regions += row(
        8,
        680,
        [
            ("18%", product_x, 105, 42),
            ("ALC./VOL.", product_x + 125, 240, 42),
            ("(2)", warning_x, 45, 28),
            ("Consumption", warning_x + 60, 220, 28),
            ("of", warning_x + 295, 35, 28),
            ("alcoholic", warning_x + 345, 145, 28),
            ("beverages", warning_x + 505, 170, 28),
        ],
    )
    regions += row(
        9,
        750,
        [
            ("200", product_x, 90, 42),
            ("ML", product_x + 110, 70, 42),
            ("impairs", warning_x, 120, 28),
            ("your", warning_x + 135, 75, 28),
            ("ability", warning_x + 225, 100, 28),
            ("to", warning_x + 340, 35, 28),
            ("drive", warning_x + 390, 80, 28),
            ("a", warning_x + 485, 20, 28),
            ("car", warning_x + 520, 50, 28),
        ],
    )
    regions += row(
        10,
        815,
        [
            ("or", warning_x, 35, 28),
            ("operate", warning_x + 50, 125, 28),
            ("machinery,", warning_x + 190, 180, 28),
            ("and", warning_x + 385, 60, 28),
            ("may", warning_x + 460, 70, 28),
            ("cause", warning_x + 545, 95, 28),
            ("health", warning_x + 655, 100, 28),
            ("problems.", warning_x + 770, 160, 28),
        ],
    )
    return regions


def warning_box(*, product_on_left: bool = True) -> BoundingBox:
    left = 1300 if product_on_left else 50
    return BoundingBox(left=left, top=380, width=1200, height=520)


def blank_image() -> bytes:
    output = BytesIO()
    Image.new("RGB", (2600, 1500), "white").save(output, format="PNG")
    return output.getvalue()


def test_reconstruction_splits_tesseract_line_across_panels():
    lines = reconstruct_ocr_lines(ocr_result(representative_regions()))

    assert lines[0].text == "12345 IMPORTS"
    assert lines[0].panel_id == 0
    assert lines[0].bounding_box == BoundingBox(left=120, top=100, width=425, height=56)
    assert lines[0].mean_confidence == 0.95
    assert lines[0].approximate_line_height == 56
    assert any(line.text == "PRODUCED IN CANADA" and line.panel_id == 1 for line in lines)
    assert not any("IMPORTS PRODUCED" in line.text for line in lines)


def test_real_label_shape_extracts_isolated_fields_from_both_panels():
    result = ocr_result(
        representative_regions(),
        raw_text=(
            "12345 IMPORTS PRODUCED IN CANADA\n"
            "RUM WITH (1) According to the Surgeon General\n"
            "COCONUT LIQUEUR ability to drive a car"
        ),
    )
    warning = analyze_government_warning(
        result,
        preprocessed_image=blank_image(),
        container_volume_ml=200,
    )
    assert warning.bounding_box is not None
    assert warning.bounding_box.left >= 1300
    assert "RUM WITH" not in (warning.localized_text or "")
    excluded = BoundingBox(
        left=warning.bounding_box.left,
        top=warning.bounding_box.top,
        width=warning.bounding_box.width,
        height=warning.bounding_box.height,
    )
    candidates = extract_candidates(result, excluded_regions=(excluded,))

    assert [item.raw_value for item in candidates.brand_name] == ["12345 IMPORTS"]
    assert [item.raw_value for item in candidates.class_type] == ["RUM WITH COCONUT LIQUEUR"]
    assert [item.normalized_percent for item in candidates.abv] == [18]
    assert [item.raw_value for item in candidates.net_contents] == ["200 ML"]
    assert [item.raw_value for item in candidates.producer_name] == ["12345 IMPORTS"]
    assert [item.raw_value for item in candidates.producer_address] == ["MIAMI, FL"]
    assert [item.raw_value for item in candidates.country_origin] == ["CANADA"]
    assert all(
        "ability to drive" not in item.raw_value.casefold() for item in candidates.class_type
    )


def test_warning_exclusion_applies_to_every_generic_text_candidate_type():
    regions = representative_regions()
    regions += row(20, 850, [("RUM", 1370, 100, 28)])
    regions += row(
        21,
        855,
        [
            ("IMPORTED", 1600, 180, 28),
            ("BY:", 1800, 50, 28),
            ("FAKE", 1870, 90, 28),
            ("IMPORTER", 1980, 160, 28),
        ],
    )
    regions += row(22, 885, [("MIAMI,", 1370, 130, 28), ("FL", 1520, 40, 28)])
    regions += row(
        23,
        885,
        [
            ("PRODUCT", 1700, 150, 28),
            ("OF", 1870, 45, 28),
            ("CANADA", 1935, 140, 28),
        ],
    )
    result = ocr_result(regions)
    candidates = extract_candidates(result, excluded_regions=(warning_box(),))
    all_generic = (
        candidates.brand_name
        + candidates.class_type
        + candidates.producer_name
        + candidates.producer_address
        + candidates.country_origin
    )

    evidence = "\n".join(item.source_line for item in all_generic).casefold()
    assert "government" not in evidence
    assert "surgeon" not in evidence
    assert "fake importer" not in evidence
    assert "product of canada" not in evidence


def test_warning_left_and_product_right_remain_spatially_isolated():
    candidates = extract_candidates(
        ocr_result(representative_regions(product_on_left=False)),
        excluded_regions=(warning_box(product_on_left=False),),
    )

    assert candidates.brand_name[0].raw_value == "12345 IMPORTS"
    assert candidates.class_type[0].raw_value == "RUM WITH COCONUT LIQUEUR"
    assert candidates.producer_address[0].raw_value == "MIAMI, FL"


def test_spatially_distant_class_lines_are_not_concatenated():
    regions = []
    regions += row(1, 100, [("RUM", 100, 120, 40)])
    regions += row(
        2,
        600,
        [("COCONUT", 100, 230, 40), ("LIQUEUR", 350, 210, 40)],
    )

    candidates = extract_candidates(ocr_result(regions))

    assert [candidate.raw_value for candidate in candidates.class_type] == [
        "RUM",
        "COCONUT LIQUEUR",
    ]


def test_ambiguous_brand_geometry_requires_review():
    regions = []
    regions += row(1, 100, [("ALPHA", 100, 180, 50), ("HOUSE", 300, 180, 50)])
    regions += row(2, 190, [("RUM", 100, 120, 35)])
    regions += row(3, 100, [("BETA", 1400, 160, 50), ("HOUSE", 1580, 180, 50)])
    regions += row(4, 190, [("VODKA", 1400, 180, 35)])
    candidates = extract_candidates(ocr_result(regions))
    expected = ApplicationData(
        brand_name="Alpha House",
        class_type="Rum",
        abv=40,
        net_contents="750 mL",
        producer_name="Example Producer",
        producer_address="Miami, FL",
        imported_product=False,
    )

    assert {item.raw_value for item in candidates.brand_name} == {"ALPHA HOUSE", "BETA HOUSE"}
    assert compare_application_data(expected, candidates).brand_name.status == "review"


def test_multiple_nearby_addresses_are_preserved_for_review():
    regions = []
    regions += row(
        1,
        100,
        [
            ("IMPORTED", 100, 180, 30),
            ("BY:", 300, 55, 30),
            ("EXAMPLE", 375, 180, 30),
            ("IMPORTS", 575, 180, 30),
        ],
    )
    regions += row(2, 155, [("MIAMI,", 100, 130, 28), ("FL", 250, 40, 28)])
    regions += row(3, 195, [("TAMPA,", 100, 130, 28), ("FL", 250, 40, 28)])
    candidates = extract_candidates(ocr_result(regions))
    expected = ApplicationData(
        brand_name="Example",
        class_type="Rum",
        abv=40,
        net_contents="750 mL",
        producer_name="Example Imports",
        producer_address="Miami, FL",
        imported_product=False,
    )

    assert [item.raw_value for item in candidates.producer_address] == ["MIAMI, FL", "TAMPA, FL"]
    assert compare_application_data(expected, candidates).producer_address.status == "review"
