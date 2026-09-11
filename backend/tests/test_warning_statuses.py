from io import BytesIO

import pytest
from PIL import Image
from test_comparison import application, complete_candidates
from test_government_warning import structured_result

from app.models.verification import (
    MANUAL_PHYSICAL_WARNING_CHECKS,
    GovernmentWarningAnalysis,
    GovernmentWarningChecks,
    WarningCheck,
)
from app.services.comparison import compare_application_data, overall_summary
from app.services.government_warning import analyze_government_warning


def warning(**overrides):
    checks = {
        name: WarningCheck(
            status=overrides.get(
                name, "review" if name in MANUAL_PHYSICAL_WARNING_CHECKS else "match"
            ),
            explanation="Test evidence",
        )
        for name in GovernmentWarningChecks.model_fields
    }
    legacy = "mismatch" if any(c.status == "mismatch" for c in checks.values()) else "review"
    return GovernmentWarningAnalysis(
        overall_status=legacy,
        localized_text="Test warning",
        bounding_box=None,
        analysis_duration_ms=0,
        checks=GovernmentWarningChecks(**checks),
    )


def test_manual_only_review_is_separate_from_automated_result():
    result = warning()
    assert result.overall_status == "review"  # Conservative legacy contract retained.
    assert result.automated_status == "match"
    assert result.manual_confirmation_required is True
    assert result.model_dump()["automated_status"] == "match"
    assert result.model_dump()["manual_confirmation_required"] is True
    assert result.checks.type_size.status == result.checks.characters_per_inch.status == "review"
    fields = compare_application_data(application(), complete_candidates())
    assert overall_summary(fields, result) == "All checks completed by this tool matched."


@pytest.mark.parametrize(
    "name",
    [n for n in GovernmentWarningChecks.model_fields if n not in MANUAL_PHYSICAL_WARNING_CHECKS],
)
@pytest.mark.parametrize("status", ["review", "mismatch"])
def test_every_automatable_problem_still_gates(name, status):
    result = warning(**{name: status})
    assert result.automated_status == status
    assert result.manual_confirmation_required is True
    fields = compare_application_data(application(), complete_candidates())
    summary = overall_summary(fields, result)
    if status == "review":
        assert summary == "One or more label checks require manual review."
    else:
        assert "differ" in summary


def test_absent_warning_and_actual_field_problems_remain_visible():
    absent = warning(presence="not_found")
    assert absent.automated_status == "not_found"
    assert absent.manual_confirmation_required is True
    fields = compare_application_data(application(), complete_candidates())
    assert "manual review" in overall_summary(fields, absent)
    for status in ["review", "not_found", "mismatch"]:
        fields.brand_name.status = status
        summary = overall_summary(fields, warning())
        assert "checks completed by this tool matched" not in summary.lower()
        assert ("differ" if status == "mismatch" else "manual review") in summary


@pytest.mark.parametrize("name", MANUAL_PHYSICAL_WARNING_CHECKS)
def test_future_physical_defect_cannot_be_hidden_by_automated_status(name):
    """A physical mismatch must surface in automated_status itself, not only
    via the legacy overall_status field. automated_status is the single
    source of truth other layers (comparison.py, the frontend) rely on."""
    result = warning(**{name: "mismatch"})
    assert result.automated_status == "mismatch"
    assert result.manual_confirmation_required is True
    fields = compare_application_data(application(), complete_candidates())
    assert "differ" in overall_summary(fields, result)


def test_manual_flag_is_derived_not_a_caller_supplied_claim():
    payload = warning().model_dump()
    payload["manual_confirmation_required"] = False
    assert GovernmentWarningAnalysis.model_validate(payload).manual_confirmation_required is True


@pytest.mark.parametrize("dpi", [72, 96, 300, 1200])
def test_raster_dpi_never_establishes_physical_compliance(dpi):
    image = Image.new("RGB", (2200, 600), "white")
    data = BytesIO()
    image.save(data, format="PNG", dpi=(dpi, dpi))
    result = analyze_government_warning(
        structured_result(),
        preprocessed_image=data.getvalue(),
        container_volume_ml=750,
    )
    assert result.manual_confirmation_required is True
    assert result.checks.type_size.status == "review"
    assert result.checks.characters_per_inch.status == "review"
    assert result.checks.type_size.measurements["physical_scale_available"] is False
