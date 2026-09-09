import pytest

from app.models.verification import (
    AbvCandidate,
    ApplicationData,
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


def test_brand_genuine_mismatch_and_missing_candidate():
    candidates = complete_candidates()
    candidates.brand_name = [text_candidate("River Bend")]
    assert compare_application_data(application(), candidates).brand_name.status == "mismatch"
    candidates.brand_name = []
    assert compare_application_data(application(), candidates).brand_name.status == "not_found"


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
