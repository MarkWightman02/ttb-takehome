from difflib import SequenceMatcher

from app.models.verification import (
    AbvCandidate,
    ApplicationData,
    CountryCandidate,
    ExtractedCandidates,
    FieldVerificationResult,
    GovernmentWarningAnalysis,
    TextCandidate,
    VerificationResults,
    VolumeCandidate,
)
from app.services.normalization import (
    STATE_NAMES,
    normalize_address,
    normalize_country,
    normalize_text,
    normalize_volume,
)


def compare_application_data(
    expected: ApplicationData, candidates: ExtractedCandidates
) -> VerificationResults:
    return VerificationResults(
        brand_name=_compare_brand(expected.brand_name, candidates.brand_name),
        class_type=_compare_text(
            field="class_type",
            label="class/type",
            expected_raw=expected.class_type,
            candidates=candidates.class_type,
            review_threshold=0.72,
        ),
        abv=_compare_abv(expected.abv, candidates.abv),
        net_contents=_compare_volume(expected.net_contents, candidates.net_contents),
        producer_name=_compare_producer_name(expected.producer_name, candidates.producer_name),
        producer_address=_compare_address(expected.producer_address, candidates.producer_address),
        country_origin=_compare_country(
            expected.country_origin, expected.imported_product, candidates.country_origin
        ),
    )


def overall_summary(
    results: VerificationResults, warning: GovernmentWarningAnalysis | None = None
) -> str:
    statuses = {
        result.status
        for result in (
            results.brand_name,
            results.class_type,
            results.abv,
            results.net_contents,
            results.producer_name,
            results.producer_address,
            results.country_origin,
        )
        if result.status != "not_applicable"
    }
    if warning is None:
        if "mismatch" in statuses:
            return "One or more application fields do not match the label."
        if statuses & {"review", "not_found"}:
            return "One or more fields require manual review."
        return "All checked application fields match the label."
    if "mismatch" in statuses or warning.automated_status == "mismatch":
        return "One or more detected fields differ from the application or prescribed warning."
    if statuses & {"review", "not_found"} or warning.automated_status in {"review", "not_found"}:
        return "One or more label checks require manual review."
    if warning.manual_confirmation_required:
        return (
            "All automated checks matched; physical Government Warning measurements "
            "require manual confirmation."
        )
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


def _compare_brand(expected_raw: str, candidates: list[TextCandidate]) -> FieldVerificationResult:
    result = _compare_text(
        field="brand_name",
        label="brand name",
        expected_raw=expected_raw,
        candidates=candidates,
        review_threshold=0.80,
    )
    if len({candidate.normalized_value for candidate in candidates}) <= 1:
        return result
    return result.model_copy(
        update={
            "status": "review",
            "explanation": (
                "Multiple similarly plausible brand lines were detected; manual review is required."
            ),
            "evidence": _unique_evidence(candidates),
        }
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


def _compare_address(expected_raw: str, candidates: list[TextCandidate]) -> FieldVerificationResult:
    expected_normalized = normalize_address(expected_raw)
    evidence = _unique_evidence(candidates)
    if not candidates:
        return FieldVerificationResult(
            field="producer_address",
            expected_raw=expected_raw,
            extracted_raw=None,
            expected_normalized=expected_normalized,
            extracted_normalized=None,
            status="not_found",
            explanation="No reliable producer / bottler address was found in the label text.",
        )

    normalized = [(normalize_address(candidate.raw_value), candidate) for candidate in candidates]
    if len({value for value, _candidate in normalized}) > 1:
        exact = next((item for item in normalized if item[0] == expected_normalized), None)
        value, selected = exact or max(
            normalized,
            key=lambda item: _text_similarity(expected_normalized, item[0]),
        )
        score = _text_similarity(expected_normalized, value)
        return FieldVerificationResult(
            field="producer_address",
            expected_raw=expected_raw,
            extracted_raw=selected.raw_value,
            expected_normalized=expected_normalized,
            extracted_normalized=value,
            status="review",
            explanation=(
                "Multiple producer / bottler addresses were detected; manual review is required."
            ),
            evidence=evidence,
            similarity_score=round(score, 3),
        )
    exact = next((item for item in normalized if item[0] == expected_normalized), None)
    if exact is not None:
        value, candidate = exact
        return FieldVerificationResult(
            field="producer_address",
            expected_raw=expected_raw,
            extracted_raw=candidate.raw_value,
            expected_normalized=expected_normalized,
            extracted_normalized=value,
            status="match",
            explanation=(
                "Address matches after capitalization, punctuation, and state-name normalization."
            ),
            evidence=evidence,
        )

    scored = [
        (_text_similarity(expected_normalized, value), value, candidate)
        for value, candidate in normalized
    ]
    score, value, best = max(scored, key=lambda item: item[0])
    expected_tokens = set(expected_normalized.split())
    detected_tokens = set(value.split())
    expected_state = _address_state(expected_normalized)
    detected_state = _address_state(value)
    conflicting_state = bool(expected_state and detected_state and expected_state != detected_state)
    partial = bool(detected_tokens) and (
        detected_tokens < expected_tokens or expected_tokens < detected_tokens
    )
    status = (
        "mismatch" if conflicting_state else ("review" if partial or score >= 0.72 else "mismatch")
    )
    explanation = (
        "The detected state differs from the application address."
        if conflicting_state
        else (
            "Only part of the expected address was detected; manual review is required."
            if partial
            else (
                "The detected address may correspond to the application, but OCR differences "
                "require manual review."
                if status == "review"
                else "The detected producer / bottler address differs from the application value."
            )
        )
    )
    return FieldVerificationResult(
        field="producer_address",
        expected_raw=expected_raw,
        extracted_raw=best.raw_value,
        expected_normalized=expected_normalized,
        extracted_normalized=value,
        status=status,
        explanation=explanation,
        evidence=evidence,
        similarity_score=round(score, 3),
    )


def _compare_country(
    expected_raw: str | None,
    imported_product: bool,
    candidates: list[CountryCandidate],
) -> FieldVerificationResult:
    if not imported_product:
        return FieldVerificationResult(
            field="country_origin",
            expected_raw="Not applicable",
            extracted_raw=None,
            expected_normalized=None,
            extracted_normalized=None,
            status="not_applicable",
            explanation=(
                "Country of origin is not checked because the application identifies a "
                "domestic product."
            ),
        )
    if expected_raw is None or not expected_raw.strip():
        raise ValueError("Country of origin is required for an imported product.")
    expected_normalized = normalize_country(expected_raw)
    if not candidates:
        return FieldVerificationResult(
            field="country_origin",
            expected_raw=expected_raw,
            extracted_raw=None,
            expected_normalized=expected_normalized,
            extracted_normalized=None,
            status="not_found",
            explanation="No reliable country-of-origin statement was found in the label text.",
        )

    distinct = {candidate.normalized_value for candidate in candidates}
    matching = next(
        (
            candidate
            for candidate in candidates
            if candidate.normalized_value == expected_normalized
        ),
        None,
    )
    selected = matching or max(
        candidates,
        key=lambda candidate: _text_similarity(expected_normalized, candidate.normalized_value),
    )
    evidence = _unique_evidence(candidates)
    if len(distinct) > 1:
        return FieldVerificationResult(
            field="country_origin",
            expected_raw=expected_raw,
            extracted_raw=selected.raw_value,
            expected_normalized=expected_normalized,
            extracted_normalized=selected.normalized_value,
            status="review",
            explanation=(
                "Multiple country-of-origin statements were detected; manual review is required."
            ),
            evidence=evidence,
        )
    if selected.normalized_value == expected_normalized:
        return FieldVerificationResult(
            field="country_origin",
            expected_raw=expected_raw,
            extracted_raw=selected.raw_value,
            expected_normalized=expected_normalized,
            extracted_normalized=selected.normalized_value,
            status="match",
            explanation=(
                f"Label identifies {selected.raw_value}; application specifies {expected_raw}."
            ),
            evidence=evidence,
        )
    score = _text_similarity(expected_normalized, selected.normalized_value)
    status = "review" if score >= 0.80 else "mismatch"
    explanation = (
        "A possible country-of-origin match was found, but OCR differences require manual review."
        if status == "review"
        else f"Application specifies {expected_raw}; label identifies {selected.raw_value}."
    )
    return FieldVerificationResult(
        field="country_origin",
        expected_raw=expected_raw,
        extracted_raw=selected.raw_value,
        expected_normalized=expected_normalized,
        extracted_normalized=selected.normalized_value,
        status=status,
        explanation=explanation,
        evidence=evidence,
        similarity_score=round(score, 3),
    )


def _compare_producer_name(
    expected_raw: str, candidates: list[TextCandidate]
) -> FieldVerificationResult:
    result = _compare_text(
        field="producer_name",
        label="producer / bottler name",
        expected_raw=expected_raw,
        candidates=candidates,
        review_threshold=0.80,
    )
    if len({candidate.normalized_value for candidate in candidates}) <= 1:
        return result
    return result.model_copy(
        update={
            "status": "review",
            "explanation": (
                "Multiple producer / bottler names were detected; manual review is required."
            ),
            "evidence": _unique_evidence(candidates),
        }
    )


def _text_similarity(left: str, right: str) -> float:
    direct = SequenceMatcher(None, left, right).ratio()
    token_order_insensitive = SequenceMatcher(
        None, " ".join(sorted(left.split())), " ".join(sorted(right.split()))
    ).ratio()
    return max(direct, token_order_insensitive)


def _address_state(normalized_address: str) -> str | None:
    state_codes = set(STATE_NAMES.values())
    for token in reversed(normalized_address.split()):
        if token.isdigit():
            continue
        return token if token in state_codes else None
    return None


def _unique_evidence(
    candidates: list[TextCandidate | AbvCandidate | VolumeCandidate | CountryCandidate],
) -> list[str]:
    return list(dict.fromkeys(candidate.source_line for candidate in candidates))


def _format_number(value: float) -> str:
    return f"{value:g}"
