import pytest

from app.services.structured_extraction import extract_candidates


@pytest.mark.parametrize(
    "line",
    [
        "45% ABV",
        "45% Alc./Vol.",
        "45% ALC/VOL",
        "ALC 45% BY VOL",
        "Alcohol 45% by Volume",
        "45 percent alcohol by volume",
        "45.5% ABV",
    ],
)
def test_extracts_common_abv_representations(line: str):
    candidates = extract_candidates(line).abv
    assert len(candidates) == 1
    assert candidates[0].normalized_percent in {45.0, 45.5}
    assert candidates[0].source_line == line


def test_rejects_impossible_abv_and_does_not_infer_proof():
    candidates = extract_candidates("145% ABV\n90 Proof").abv
    assert candidates == []


def test_preserves_multiple_abv_candidates():
    candidates = extract_candidates("45% ABV\n40% Alc./Vol.").abv
    assert [candidate.normalized_percent for candidate in candidates] == [45.0, 40.0]


@pytest.mark.parametrize(
    ("line", "expected_ml"),
    [
        ("750 mL", 750.0),
        ("750ml", 750.0),
        ("1000mI", 1000.0),
        ("375 ML", 375.0),
        ("1 L", 1000.0),
        ("1.0 L", 1000.0),
        ("1 Liter", 1000.0),
        ("1 Litre", 1000.0),
        ("1000 mL", 1000.0),
    ],
)
def test_extracts_metric_volume(line: str, expected_ml: float):
    candidate = extract_candidates(line).net_contents[0]
    assert candidate.normalized_ml == expected_ml
    assert candidate.source_line == line


@pytest.mark.parametrize(
    ("line", "expected_ml"),
    [
        ("1 PINT", 473.176473),
        ("1 PT", 473.176473),
        ("16 FL OZ", 473.176473),
        ("16 fluid ounces", 473.176473),
    ],
)
def test_extracts_us_fluid_volume(line: str, expected_ml: float):
    candidate = extract_candidates(line).net_contents[0]
    assert candidate.normalized_ml == expected_ml
    assert candidate.source_line == line


def test_preserves_multiple_volume_candidates():
    candidates = extract_candidates("750 mL\n375 mL").net_contents
    assert [candidate.normalized_ml for candidate in candidates] == [750.0, 375.0]


def test_volume_ocr_repair_does_not_treat_lowercase_mi_as_milliliters():
    assert extract_candidates("750 mi").net_contents == []


def test_brand_and_class_candidates_use_filtered_lines():
    candidates = extract_candidates(
        "GOVERNMENT WARNING: Do not drink during pregnancy\n"
        "45% Alc./Vol.\n"
        "OLD TOM DISTILLERY\n"
        "Kentucky Straight Bourbon Whiskey\n"
        "750 mL"
    )
    assert [candidate.raw_value for candidate in candidates.brand_name] == ["OLD TOM DISTILLERY"]
    assert [candidate.raw_value for candidate in candidates.class_type] == [
        "Kentucky Straight Bourbon Whiskey"
    ]


def test_government_warning_body_is_not_a_brand_candidate():
    candidates = extract_candidates(
        "OLD TOM DISTILLERY\n"
        "GOVERNMENT WARNING:\n"
        "(1) According to the Surgeon General, women should not drink alcoholic beverages\n"
        "during pregnancy because of the risk of birth defects.\n"
        "(2) Consumption of alcoholic beverages impairs your ability to drive a car or\n"
        "operate machinery, and may cause health problems."
    )
    assert [candidate.raw_value for candidate in candidates.brand_name] == ["OLD TOM DISTILLERY"]


def test_brand_extraction_does_not_blindly_use_first_line():
    candidates = extract_candidates("45% ABV\nStone's Throw\nVodka\n750 mL")
    assert candidates.brand_name[0].raw_value == "Stone's Throw"


@pytest.mark.parametrize(
    "cue",
    [
        "Bottled by",
        "Produced by",
        "Distilled by",
        "Brewed by",
        "Vinted by",
        "Cellared by",
        "Imported by",
    ],
)
def test_extracts_inline_producer_and_following_address(cue: str):
    candidates = extract_candidates(f"{cue} Old Tom Distillery\nLouisville, KY")
    assert candidates.producer_name[0].raw_value == "Old Tom Distillery"
    assert candidates.producer_name[0].source_line.startswith(cue)
    assert candidates.producer_address[0].raw_value == "Louisville, KY"


def test_extracts_multiline_producer_name_and_address():
    candidates = extract_candidates(
        "Produced and bottled by\nExample Spirits LLC\nLouisville, Kentucky"
    )
    assert candidates.producer_name[0].raw_value == "Example Spirits LLC"
    assert candidates.producer_name[0].source_line == (
        "Produced and bottled by\nExample Spirits LLC"
    )
    assert candidates.producer_address[0].raw_value == "Louisville, Kentucky"


def test_extracts_distilled_and_bottled_multiline_entity_block():
    candidates = extract_candidates("DISTILLED AND BOTTLED BY:\nABC DISTILLERY\nFREDERICK,MD")

    assert candidates.producer_name[0].raw_value == "ABC DISTILLERY"
    assert candidates.producer_address[0].raw_value == "FREDERICK,MD"


def test_splits_same_line_company_and_city_state_address():
    candidates = extract_candidates("BOTTLED BY XYZ CELLARS, CITY, STATE")

    assert candidates.producer_name[0].raw_value == "XYZ CELLARS"
    assert candidates.producer_address[0].raw_value == "CITY, STATE"


def test_extracts_city_and_state_without_comma():
    candidates = extract_candidates("Produced by Stone's Throw Spirits LLC\nNASHVILLE TN")
    assert candidates.producer_address[0].raw_value == "NASHVILLE TN"


@pytest.mark.parametrize(
    ("line", "country"),
    [
        ("Product of France", "France"),
        ("PRODUCT OF ITALY", "ITALY"),
        ("Imported from Mexico", "Mexico"),
        ("Made in Ireland", "Ireland"),
        ("PRODUCED IN CANADA", "CANADA"),
    ],
)
def test_extracts_country_of_origin_cues(line: str, country: str):
    candidate = extract_candidates(line).country_origin[0]
    assert candidate.raw_value == country
    assert candidate.source_line == line


def test_missing_producer_and_origin_do_not_fabricate_candidates():
    candidates = extract_candidates("OLD TOM DISTILLERY\nBourbon Whiskey\n750 mL")
    assert candidates.producer_name == []
    assert candidates.producer_address == []
    assert candidates.country_origin == []
