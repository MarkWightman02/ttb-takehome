import pytest

from scripts.evaluate_warnings import warning_volume


def test_warning_evaluation_preserves_supported_volume():
    assert warning_volume("750 ML") == (750, None)


def test_compound_fixture_metadata_is_explicitly_diagnostic_not_an_api_fix():
    volume, note = warning_volume("1 PINT (473 ML)")
    assert volume == 473
    assert "not supported" in note


def test_warning_evaluation_does_not_invent_missing_metric_volume():
    with pytest.raises(ValueError):
        warning_volume("unreadable contents")
