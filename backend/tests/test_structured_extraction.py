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


def test_preserves_multiple_volume_candidates():
    candidates = extract_candidates("750 mL\n375 mL").net_contents
    assert [candidate.normalized_ml for candidate in candidates] == [750.0, 375.0]


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
