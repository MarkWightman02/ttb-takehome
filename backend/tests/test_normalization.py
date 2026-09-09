import pytest

from app.services.normalization import (
    normalize_abv,
    normalize_address,
    normalize_country,
    normalize_text,
    normalize_volume,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("  STONE'S   THROW  ", "stones throw"),
        ("Stone’s Throw", "stones throw"),
        ("Stone—Throw", "stone throw"),
        ("OLD.TOM, DISTILLERY", "old tom distillery"),
        ("ＣＡＦÉ", "café"),
    ],
)
def test_text_normalization(value: str, expected: str):
    assert normalize_text(value) == expected


@pytest.mark.parametrize(("value", "expected"), [("45", 45.0), ("45.0", 45.0), ("45%", 45.0)])
def test_abv_normalization(value: str, expected: float):
    assert normalize_abv(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("750 mL", 750.0),
        ("750ml", 750.0),
        ("1 L", 1000.0),
        ("1 Liter", 1000.0),
        ("1 PINT", 473.176473),
        ("1 pt", 473.176473),
        ("16 FL OZ", 473.176473),
        ("16 fluid ounces", 473.176473),
    ],
)
def test_volume_normalization(value: str, expected: float):
    assert normalize_volume(value) == expected


@pytest.mark.parametrize("value", ["0", "101", "not a number"])
def test_abv_normalization_rejects_impossible_values(value: str):
    with pytest.raises(ValueError):
        normalize_abv(value)


def test_volume_normalization_rejects_incompatible_units():
    with pytest.raises(ValueError):
        normalize_volume("1 gallon")


def test_address_normalization_handles_state_name_and_punctuation():
    assert normalize_address("Louisville, Kentucky") == normalize_address("LOUISVILLE KY")


def test_country_normalization_handles_harmless_variants():
    assert normalize_country(" U.S.A. ") == normalize_country("United States of America")
