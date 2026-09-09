from evaluation.corpus import evaluation_cases, render_case


def test_evaluation_corpus_covers_required_styles_outcomes_and_degradation():
    cases = evaluation_cases()
    styles = {case.beverage_style for case in cases}
    expected_statuses = {status for case in cases for status in case.expected.values()}

    assert styles == {"distilled spirits", "wine", "malt beverage"}
    assert {"match", "review", "mismatch", "not_found", "not_applicable"} <= expected_statuses
    assert any(case.application.imported_product for case in cases)
    assert any(not case.application.imported_product for case in cases)
    assert any(case.degradation for case in cases)
    assert any(not case.warning_lines for case in cases)
    assert {case.panel_layout for case in cases} == {
        "single",
        "product_left",
        "product_right",
    }


def test_generated_evaluation_images_are_deterministic():
    case = evaluation_cases()[0]
    first = render_case(case)
    second = render_case(case)

    assert first.media_type == "image/png"
    assert first.data == second.data
