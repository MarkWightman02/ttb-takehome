import pytest

from app.models.verification import (
    AbvCandidate,
    ApplicationData,
    CountryCandidate,
    ExtractedCandidates,
    TextCandidate,
    VolumeCandidate,
)
from app.services.comparison import compare_application_data, overall_summary
from app.services.normalization import normalize_text


def text_candidate(value: str) -> TextCandidate:
    return TextCandidate(
        raw_value=value,
        normalized_value=normalize_text(value),
        source_line=value,
        line_number=1,
    )


def application(**overrides: object) -> ApplicationData:
    values: dict[str, object] = {
        "brand_name": "Stone's Throw",
        "class_type": "Kentucky Straight Bourbon Whiskey",
        "abv": 45.0,
        "net_contents": "750 mL",
        "producer_name": "Old Tom Distillery LLC",
        "producer_address": "Louisville, Kentucky",
        "imported_product": False,
        "country_origin": None,
    }
    values.update(overrides)
    return ApplicationData(**values)


def complete_candidates() -> ExtractedCandidates:
    return ExtractedCandidates(
        brand_name=[text_candidate("STONE’S THROW")],
        class_type=[text_candidate("KENTUCKY STRAIGHT BOURBON WHISKEY")],
        abv=[
            AbvCandidate(
                raw_value="45% Alc./Vol.",
                normalized_percent=45,
                source_line="45% Alc./Vol.",
                line_number=3,
            )
        ],
        net_contents=[
            VolumeCandidate(
                raw_value="750ml",
                normalized_ml=750,
                source_line="750ml",
                line_number=4,
            )
        ],
        producer_name=[text_candidate("OLD TOM DISTILLERY LLC")],
        producer_address=[text_candidate("Louisville, KY")],
    )


@pytest.mark.parametrize(
    "candidate",
    ["Stone's Throw", "STONE'S THROW", "  Stone's   Throw  ", "Stone’s Throw", "Stone's Throw."],
)
def test_brand_normalized_matches(candidate: str):
    candidates = complete_candidates()
    candidates.brand_name = [text_candidate(candidate)]
    assert compare_application_data(application(), candidates).brand_name.status == "match"


def test_brand_minor_ocr_damage_requires_review():
    candidates = complete_candidates()
    candidates.brand_name = [text_candidate("St0ne's Throw")]
    result = compare_application_data(application(), candidates).brand_name
    assert result.status == "review"
    assert result.similarity_score is not None


@pytest.mark.parametrize(
    ("expected", "detected"),
    [
        ("12345 IMPORTS", "1234 IMPORTS"),
        ("ABC DISTILLERY", "ABC DISTILLING"),
        ("ABC WINERY", "ABC WINES"),
        ("MALT & HOP BREWERY", "MALT HOP BREWERY"),
        ("MALT & HOP BREWERY", "MALT @ HOP BREWERY"),
    ],
)
def test_substantive_brand_differences_never_match(expected: str, detected: str):
    candidates = complete_candidates()
    candidates.brand_name = [text_candidate(detected)]
    result = compare_application_data(application(brand_name=expected), candidates).brand_name
    assert result.status in {"review", "mismatch"}
    assert result.expected_normalized != result.extracted_normalized


def test_shortened_type_and_changed_numbers_never_match():
    candidates = complete_candidates()
    candidates.class_type = [text_candidate("PALE ALE")]
    candidates.net_contents[0].normalized_ml = 700
    candidates.net_contents[0].raw_value = "700 ML"
    candidates.abv[0].normalized_percent = 18
    candidates.abv[0].raw_value = "18% ABV"
    results = compare_application_data(application(class_type="INDIA PALE ALE", abv=13), candidates)
    assert results.class_type.status in {"review", "mismatch"}
    assert results.net_contents.status == "mismatch"
    assert results.abv.status == "mismatch"


@pytest.mark.parametrize(
    ("field", "expected", "detected"),
    [
        ("class_type", "STRAIGHT RYE WHISKY", "RYE WHISKY"),
        ("net_contents", "500 ML", "550 ML"),
        ("abv", 12.5, "12% ABV"),
        ("class_type", "India Pale Ale", "India Pale Ale Extra®"),
    ],
)
def test_subtle_differences_survive_extraction(field, expected, detected):
    from app.services.structured_extraction import extract_candidates

    candidates = extract_candidates(detected)
    result = getattr(compare_application_data(application(**{field: expected}), candidates), field)
    assert result.status in {"review", "mismatch"}


def test_trademark_does_not_remove_the_class_word_it_is_attached_to():
    from app.services.structured_extraction import extract_candidates

    candidates = extract_candidates("India Pale Ale®")
    result = compare_application_data(application(class_type="India Pale Ale"), candidates)
    assert result.class_type.status == "match"
    assert result.class_type.extracted_raw == "India Pale Ale®"


@pytest.mark.parametrize("label", ["1 Pt. 9.4 FI. Oz", "2 PINT 4 F1 OZ"])
def test_partially_read_compound_volume_cannot_match_only_the_pint_component(label):
    from app.services.structured_extraction import extract_candidates

    result = compare_application_data(
        application(net_contents=label.split()[0] + " pint"), extract_candidates(label)
    )
    assert result.net_contents.status == "not_found"


def test_complete_separate_imperial_values_remain_ambiguous():
    from app.services.structured_extraction import extract_candidates

    result = compare_application_data(
        application(net_contents="1 pint"), extract_candidates("1 Pt. 9.4 FL OZ")
    )
    assert result.net_contents.status == "review"


def test_brand_genuine_mismatch_and_missing_candidate():
    candidates = complete_candidates()
    candidates.brand_name = [text_candidate("River Bend")]
    assert compare_application_data(application(), candidates).brand_name.status == "mismatch"
    candidates.brand_name = []
    assert compare_application_data(application(), candidates).brand_name.status == "not_found"


def test_multiple_similarly_ranked_brand_candidates_require_review():
    candidates = complete_candidates()
    candidates.brand_name = [text_candidate("Stone's Throw"), text_candidate("Stone Throw Co")]

    result = compare_application_data(application(), candidates).brand_name

    assert result.status == "review"
    assert "Multiple similarly plausible" in result.explanation


@pytest.mark.parametrize(
    "candidate",
    [
        "Kentucky Straight Bourbon Whiskey",
        "KENTUCKY STRAIGHT BOURBON WHISKEY",
        "Kentucky Straight Bourbon-Whiskey",
    ],
)
def test_class_type_normalized_matches(candidate: str):
    candidates = complete_candidates()
    candidates.class_type = [text_candidate(candidate)]
    assert compare_application_data(application(), candidates).class_type.status == "match"


def test_class_type_minor_damage_review_mismatch_and_missing():
    candidates = complete_candidates()
    candidates.class_type = [text_candidate("Kentucky Straight Bourban Whiskey")]
    assert compare_application_data(application(), candidates).class_type.status == "review"
    candidates.class_type = [text_candidate("Vodka")]
    assert compare_application_data(application(), candidates).class_type.status == "mismatch"
    candidates.class_type = []
    assert compare_application_data(application(), candidates).class_type.status == "not_found"


def test_numeric_equivalence_and_actual_mismatches():
    results = compare_application_data(application(net_contents="0.75 L"), complete_candidates())
    assert results.abv.status == "match"
    assert results.net_contents.status == "match"

    mismatches = compare_application_data(
        application(abv=46, net_contents="375 mL"), complete_candidates()
    )
    assert mismatches.abv.status == "mismatch"
    assert mismatches.net_contents.status == "mismatch"
    assert overall_summary(mismatches) == "One or more application fields do not match the label."


def test_us_pint_and_fluid_ounces_compare_using_exact_conversion():
    candidates = complete_candidates()
    candidates.net_contents = [
        VolumeCandidate(
            raw_value="16 FL OZ",
            normalized_ml=473.176473,
            source_line="16 FL OZ",
            line_number=4,
        )
    ]

    result = compare_application_data(application(net_contents="1 PINT"), candidates)

    assert result.net_contents.status == "match"
    assert result.net_contents.expected_normalized == 473.176473


def test_missing_numeric_candidates_are_not_found():
    candidates = complete_candidates()
    candidates.abv = []
    candidates.net_contents = []
    results = compare_application_data(application(), candidates)
    assert results.abv.status == "not_found"
    assert results.net_contents.status == "not_found"
    assert overall_summary(results) == "One or more fields require manual review."


def test_multiple_numeric_candidates_require_review_even_when_one_matches():
    candidates = complete_candidates()
    candidates.abv.append(
        AbvCandidate(
            raw_value="40% ABV",
            normalized_percent=40,
            source_line="40% ABV",
            line_number=5,
        )
    )
    candidates.net_contents.append(
        VolumeCandidate(
            raw_value="375 mL",
            normalized_ml=375,
            source_line="375 mL",
            line_number=6,
        )
    )
    results = compare_application_data(application(), candidates)
    assert results.abv.status == "review"
    assert results.net_contents.status == "review"
    assert len(results.abv.evidence) == 2


@pytest.mark.parametrize(
    "candidate",
    ["Old Tom Distillery LLC", "OLD TOM DISTILLERY, LLC.", "Old  Tom Distillery LLC"],
)
def test_producer_name_normalized_matches(candidate: str):
    candidates = complete_candidates()
    candidates.producer_name = [text_candidate(candidate)]
    assert compare_application_data(application(), candidates).producer_name.status == "match"


def test_producer_name_review_mismatch_and_missing():
    candidates = complete_candidates()
    candidates.producer_name = [text_candidate("Old T0m Distillery LLC")]
    assert compare_application_data(application(), candidates).producer_name.status == "review"
    candidates.producer_name = [text_candidate("River Bend Imports")]
    assert compare_application_data(application(), candidates).producer_name.status == "mismatch"
    candidates.producer_name = []
    assert compare_application_data(application(), candidates).producer_name.status == "not_found"


def test_multiple_producer_entities_require_review_even_when_one_matches():
    candidates = complete_candidates()
    candidates.producer_name.append(text_candidate("Central Coast Bottling"))
    candidates.producer_address.append(text_candidate("Fresno, CA"))
    results = compare_application_data(application(), candidates)
    assert results.producer_name.status == "review"
    assert results.producer_address.status == "review"
    assert len(results.producer_name.evidence) == 2
    assert len(results.producer_address.evidence) == 2


def test_address_normalization_partial_mismatch_and_missing():
    candidates = complete_candidates()
    assert compare_application_data(application(), candidates).producer_address.status == "match"
    candidates.producer_address = [text_candidate("Louisville")]
    assert compare_application_data(application(), candidates).producer_address.status == "review"
    candidates.producer_address = [text_candidate("Nashville, TN")]
    assert compare_application_data(application(), candidates).producer_address.status == "mismatch"
    candidates.producer_address = [text_candidate("Louisville, TN")]
    assert compare_application_data(application(), candidates).producer_address.status == "mismatch"
    candidates.producer_address = []
    result = compare_application_data(application(), candidates)
    assert result.producer_address.status == "not_found"


def country_candidate(value: str) -> CountryCandidate:
    return CountryCandidate(
        raw_value=value,
        normalized_value=value.casefold(),
        source_line=f"Product of {value}",
        line_number=7,
    )


def test_domestic_country_is_not_applicable_and_does_not_degrade_summary():
    results = compare_application_data(application(), complete_candidates())
    assert results.country_origin.status == "not_applicable"
    assert overall_summary(results) == "All checked application fields match the label."


def test_imported_country_match_mismatch_review_and_missing():
    candidates = complete_candidates()
    candidates.country_origin = [country_candidate("France")]
    expected = application(imported_product=True, country_origin="FRANCE")
    assert compare_application_data(expected, candidates).country_origin.status == "match"
    expected.country_origin = "Italy"
    assert compare_application_data(expected, candidates).country_origin.status == "mismatch"
    candidates.country_origin = [country_candidate("Franee")]
    expected.country_origin = "France"
    assert compare_application_data(expected, candidates).country_origin.status == "review"
    candidates.country_origin = []
    assert compare_application_data(expected, candidates).country_origin.status == "not_found"
