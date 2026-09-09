from difflib import SequenceMatcher

from app.models.verification import (
    AbvCandidate,
    ApplicationData,
    ExtractedCandidates,
    FieldVerificationResult,
    GovernmentWarningAnalysis,
    TextCandidate,
    VerificationResults,
    VolumeCandidate,
)
from app.services.normalization import normalize_text, normalize_volume


def compare_application_data(
    expected: ApplicationData, candidates: ExtractedCandidates
) -> VerificationResults:
    return VerificationResults(
        brand_name=_compare_text(
            field="brand_name",
            label="brand name",
            expected_raw=expected.brand_name,
            candidates=candidates.brand_name,
            review_threshold=0.80,
        ),
        class_type=_compare_text(
            field="class_type",
            label="class/type",
            expected_raw=expected.class_type,
            candidates=candidates.class_type,
            review_threshold=0.72,
        ),
        abv=_compare_abv(expected.abv, candidates.abv),
        net_contents=_compare_volume(expected.net_contents, candidates.net_contents),
    )


def overall_summary(
    results: VerificationResults, warning: GovernmentWarningAnalysis | None = None
) -> str:
    statuses = {
        results.brand_name.status,
        results.class_type.status,
        results.abv.status,
        results.net_contents.status,
    }
    if warning is None:
        if "mismatch" in statuses:
            return "One or more application fields do not match the label."
        if statuses & {"review", "not_found"}:
            return "One or more fields require manual review."
        return "All checked application fields match the label."
    if "mismatch" in statuses or warning.overall_status == "mismatch":
        return "One or more detected fields differ from the application or prescribed warning."
    if statuses & {"review", "not_found"} or (warning.overall_status in {"review", "not_found"}):
        if all(
            getattr(warning.checks, name).status == "match"
            for name in ("presence", "wording", "heading_capitalization")
        ):
            return (
                "All automated text checks matched; some visual requirements still require "
                "reviewer confirmation."
            )
        return "One or more label checks require manual review."
    return "All checked application fields match the label."


def _compare_text(
    *,
    field: str,
    label: str,
    expected_raw: str,
    candidates: list[TextCandidate],
    review_threshold: float,
) -> FieldVerificationResult:
    expected_normalized = normalize_text(expected_raw)
    evidence = _unique_evidence(candidates)
    if not candidates:
        return FieldVerificationResult(
            field=field,
            expected_raw=expected_raw,
            extracted_raw=None,
            expected_normalized=expected_normalized,
            extracted_normalized=None,
            status="not_found",
            explanation=f"No reliable {label} candidate was found in the extracted label text.",
        )

    exact = next(
        (
            candidate
            for candidate in candidates
            if candidate.normalized_value == expected_normalized
        ),
        None,
    )
    if exact is not None:
        explanation = (
            "Matches exactly."
            if exact.raw_value == expected_raw
            else "Matches after capitalization, whitespace, and punctuation normalization."
        )
        return FieldVerificationResult(
            field=field,
            expected_raw=expected_raw,
            extracted_raw=exact.raw_value,
            expected_normalized=expected_normalized,
            extracted_normalized=exact.normalized_value,
            status="match",
            explanation=explanation,
            evidence=evidence,
        )

    scored = [
        (_text_similarity(expected_normalized, candidate.normalized_value), candidate)
        for candidate in candidates
    ]
    score, best = max(scored, key=lambda item: item[0])
    if score >= review_threshold:
        status = "review"
        explanation = f"Possible {label} match found, but OCR differences require manual review."
    else:
        status = "mismatch"
        explanation = f"The detected {label} differs from the application value."
    return FieldVerificationResult(
        field=field,
        expected_raw=expected_raw,
        extracted_raw=best.raw_value,
        expected_normalized=expected_normalized,
        extracted_normalized=best.normalized_value,
        status=status,
        explanation=explanation,
        evidence=evidence,
        similarity_score=round(score, 3),
    )


def _compare_abv(expected: float, candidates: list[AbvCandidate]) -> FieldVerificationResult:
    expected_label = f"{_format_number(expected)}%"
    if not candidates:
        return FieldVerificationResult(
            field="abv",
            expected_raw=expected_label,
            extracted_raw=None,
            expected_normalized=expected,
            extracted_normalized=None,
            status="not_found",
            explanation="No reliable ABV value was found in the extracted label text.",
        )
    distinct = {candidate.normalized_percent for candidate in candidates}
    matching = next(
        (candidate for candidate in candidates if candidate.normalized_percent == expected), None
    )
    selected = matching or candidates[0]
    evidence = _unique_evidence(candidates)
    if len(distinct) > 1:
        values = ", ".join(f"{_format_number(value)}%" for value in sorted(distinct))
        return FieldVerificationResult(
            field="abv",
            expected_raw=expected_label,
            extracted_raw=selected.raw_value,
            expected_normalized=expected,
            extracted_normalized=selected.normalized_percent,
            status="review",
            explanation=f"Multiple ABV values were detected ({values}); manual review is required.",
            evidence=evidence,
        )
    status = "match" if selected.normalized_percent == expected else "mismatch"
    detected_label = f"{_format_number(selected.normalized_percent)}% ABV"
    explanation = (
        f"Label shows {detected_label}; application specifies {expected_label}."
        if status == "match"
        else f"Application specifies {expected_label}; label shows {detected_label}."
    )
    return FieldVerificationResult(
        field="abv",
        expected_raw=expected_label,
        extracted_raw=selected.raw_value,
        expected_normalized=expected,
        extracted_normalized=selected.normalized_percent,
        status=status,
        explanation=explanation,
        evidence=evidence,
    )


def _compare_volume(
    expected_raw: str, candidates: list[VolumeCandidate]
) -> FieldVerificationResult:
    expected_ml = normalize_volume(expected_raw)
    if not candidates:
        return FieldVerificationResult(
            field="net_contents",
            expected_raw=expected_raw,
            extracted_raw=None,
            expected_normalized=expected_ml,
            extracted_normalized=None,
            status="not_found",
            explanation="No reliable net contents value was found in the extracted label text.",
        )
    distinct = {candidate.normalized_ml for candidate in candidates}
    matching = next(
        (candidate for candidate in candidates if candidate.normalized_ml == expected_ml), None
    )
    selected = matching or candidates[0]
    evidence = _unique_evidence(candidates)
    if len(distinct) > 1:
        values = ", ".join(f"{_format_number(value)} mL" for value in sorted(distinct))
        explanation = f"Multiple volume values were detected ({values});"
        explanation += " manual review is required."
        return FieldVerificationResult(
            field="net_contents",
            expected_raw=expected_raw,
            extracted_raw=selected.raw_value,
            expected_normalized=expected_ml,
            extracted_normalized=selected.normalized_ml,
            status="review",
            explanation=explanation,
            evidence=evidence,
        )
    status = "match" if selected.normalized_ml == expected_ml else "mismatch"
    expected_label = f"{_format_number(expected_ml)} mL"
    detected_label = f"{_format_number(selected.normalized_ml)} mL"
    explanation = (
        f"Label volume equals the application value after conversion to {expected_label}."
        if status == "match"
        else f"Application specifies {expected_label}; label shows {detected_label}."
    )
    return FieldVerificationResult(
        field="net_contents",
        expected_raw=expected_raw,
        extracted_raw=selected.raw_value,
        expected_normalized=expected_ml,
        extracted_normalized=selected.normalized_ml,
        status=status,
        explanation=explanation,
        evidence=evidence,
    )


def _text_similarity(left: str, right: str) -> float:
    direct = SequenceMatcher(None, left, right).ratio()
    token_order_insensitive = SequenceMatcher(
        None, " ".join(sorted(left.split())), " ".join(sorted(right.split()))
    ).ratio()
    return max(direct, token_order_insensitive)


def _unique_evidence(candidates: list[TextCandidate | AbvCandidate | VolumeCandidate]) -> list[str]:
    return list(dict.fromkeys(candidate.source_line for candidate in candidates))


def _format_number(value: float) -> str:
    return f"{value:g}"
