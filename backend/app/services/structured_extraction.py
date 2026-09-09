import re
import statistics

from app.models.verification import (
    AbvCandidate,
    CountryCandidate,
    ExtractedCandidates,
    TextCandidate,
    VolumeCandidate,
)
from app.services.normalization import (
    STATE_NAMES,
    normalize_address,
    normalize_country,
    normalize_text,
)
from app.services.ocr import BoundingBox, OcrResult
from app.services.spatial_layout import OcrLine, overlaps_box, reconstruct_ocr_lines

ABV_NUMBER = r"\d{1,3}(?:\.\d+)?"
VOLUME_NUMBER = r"\d+(?:\.\d+)?"
ABV_PATTERNS = (
    re.compile(
        rf"(?P<value>{ABV_NUMBER})\s*%\s*(?:a\.?\s*b\.?\s*v\.?|"
        r"alc(?:ohol)?\.?\s*(?:/|by)?\s*vol(?:ume)?\.?)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?:alc(?:ohol)?\.?)\s*(?P<value>{ABV_NUMBER})\s*%\s*"
        r"(?:by\s*)?vol(?:ume)?\.?,?",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?P<value>{ABV_NUMBER})\s+percent\s+alcohol\s+by\s+volume",
        re.IGNORECASE,
    ),
)
VOLUME_PATTERN = re.compile(
    rf"(?<![\w.])(?P<value>{VOLUME_NUMBER})\s*"
    r"(?P<unit>ml|(?-i:mI)|millilit(?:er|re)s?|l|lit(?:er|re)s?)(?!\w)",
    re.IGNORECASE,
)
CLASS_TYPE_CUES = re.compile(
    r"\b(?:whisk(?:e)?y|bourbon|vodka|gin|rum|tequila|mezcal|brandy|"
    r"ale|lager|beer|stout|porter|cider|wine|sauvignon|chardonnay|"
    r"merlot|riesling|ros[ée]|liqueur|cordial)\b",
    re.IGNORECASE,
)
EXCLUDED_BRAND_PHRASES = re.compile(
    r"\b(?:government\s+warning|alcohol\s+by\s+volume|alc\.?\s*/?\s*vol|"
    r"contains\s+sulfites|bottled\s+by|produced\s+by|distilled\s+by|"
    r"brewed\s+by|vinted\s+by|cellared\s+by|imported\s+by|imported\s+from|"
    r"product\s+of|produced\s+in|made\s+in|proof|net\s+contents?|"
    r"according\s+to\s+the\s+surgeon|surgeon\s+general|during\s+pregnancy|"
    r"risk\s+of\s+birth\s+defects|birth\s+defects|alcoholic\s+beverages|"
    r"consumption\s+of\s+alcoholic\s+beverages|ability\s+to\s+drive|"
    r"operate\s+machinery|may\s+cause\s+health\s+problems)\b",
    re.IGNORECASE,
)
GENERIC_BRAND_LINES = {
    "premium",
    "handcrafted",
    "small batch",
    "reserve",
    "established",
}
PRODUCER_CUE = re.compile(
    r"\b(?P<role>(?:produced\s+and\s+bottled|bottled|produced|distilled|brewed|"
    r"vinted|cellared|imported)\s+by)\b[\s,:-]*(?P<name>.*)$",
    re.IGNORECASE,
)
ORIGIN_PATTERN = re.compile(
    r"\b(?:product\s+of|produced\s+in|imported\s+from|made\s+in)\s+"
    r"(?P<country>[A-Za-z][A-Za-z '-]{1,60}?)"
    r"(?=\s*(?:[.,;:]|(?:imported|bottled|produced)\s+by\b|$))",
    re.IGNORECASE,
)
ADDRESS_CUE = re.compile(
    r"(?:\b\d{5}(?:-\d{4})?\s*$|\b(?:street|st\.?|road|rd\.?|avenue|ave\.?|"
    r"boulevard|blvd\.?|lane|ln\.?|drive|dr\.?|highway|hwy\.?|p\.?\s*o\.?\s*box)\b|"
    rf"[A-Za-z .'-]+,?\s+(?:{'|'.join(sorted(set(STATE_NAMES.values())))})"
    r"(?:\s+\d{5})?\s*$|"
    rf",\s*(?:{'|'.join(STATE_NAMES)})\s*$)",
    re.IGNORECASE,
)


def extract_candidates(
    source: str | OcrResult,
    *,
    excluded_regions: tuple[BoundingBox, ...] = (),
) -> ExtractedCandidates:
    """Extract deterministic candidates from raw text or spatial OCR evidence."""

    if isinstance(source, OcrResult):
        lines = reconstruct_ocr_lines(source)
        image_height = source.image_height
    else:
        lines = _plain_text_lines(source)
        image_height = None
    semantic_lines = [
        line
        for line in lines
        if not any(overlaps_box(line, excluded) for excluded in excluded_regions)
    ]
    producer_names, producer_addresses = _extract_producer_candidates(
        semantic_lines, image_height=image_height
    )
    return ExtractedCandidates(
        brand_name=_extract_brand_candidates(
            semantic_lines,
            producer_names=producer_names,
            producer_line_numbers={candidate.line_number for candidate in producer_names},
            image_height=image_height,
        ),
        class_type=_extract_class_type_candidates(semantic_lines),
        abv=_extract_abv_candidates(semantic_lines),
        net_contents=_extract_volume_candidates(semantic_lines),
        producer_name=producer_names,
        producer_address=producer_addresses,
        country_origin=_extract_country_candidates(semantic_lines),
    )


def _extract_producer_candidates(
    lines: list[OcrLine],
    *,
    image_height: int | None,
) -> tuple[list[TextCandidate], list[TextCandidate]]:
    names: list[TextCandidate] = []
    addresses: list[TextCandidate] = []
    for index, line in enumerate(lines):
        match = PRODUCER_CUE.search(line.text)
        if match is None:
            continue
        inline_name = match.group("name").strip(" ,:-")
        next_index = index + 1
        if inline_name:
            names.append(_text_candidate(inline_name, line.text, line.sequence_number))
        elif next_index < len(lines) and not ADDRESS_CUE.search(lines[next_index].text):
            name_line = lines[next_index]
            names.append(
                _text_candidate(
                    name_line.text,
                    f"{line.text}\n{name_line.text}",
                    name_line.sequence_number,
                )
            )
            next_index += 1
        nearby = _nearby_address_lines(
            line,
            lines[next_index:],
            image_height=image_height,
        )
        addresses.extend(
            TextCandidate(
                raw_value=candidate.text,
                normalized_value=normalize_address(candidate.text),
                source_line=candidate.text,
                line_number=candidate.sequence_number,
            )
            for candidate in nearby
        )
    return _deduplicate_text(names), _deduplicate_text(addresses)


def _nearby_address_lines(
    producer_line: OcrLine,
    following: list[OcrLine],
    *,
    image_height: int | None,
) -> list[OcrLine]:
    if producer_line.bounding_box is None:
        return [line for line in following[:2] if ADDRESS_CUE.search(line.text)][:1]

    box = producer_line.bounding_box
    maximum_distance = max(
        (producer_line.approximate_line_height or box.height) * 7,
        (image_height or 0) * 0.12,
    )
    candidates = []
    for line in following:
        candidate_box = line.bounding_box
        if candidate_box is None or line.panel_id != producer_line.panel_id:
            continue
        vertical_distance = candidate_box.top - (box.top + box.height)
        if vertical_distance < -box.height or vertical_distance > maximum_distance:
            continue
        if ADDRESS_CUE.search(line.text):
            candidates.append((abs(vertical_distance), line))
    if not candidates:
        return []
    candidates.sort(key=lambda item: item[0])
    nearest_distance = candidates[0][0]
    tolerance = max(producer_line.approximate_line_height or box.height, 20) * 2
    return [line for distance, line in candidates if distance <= nearest_distance + tolerance]


def _extract_country_candidates(lines: list[OcrLine]) -> list[CountryCandidate]:
    candidates: list[CountryCandidate] = []
    for line in lines:
        for match in ORIGIN_PATTERN.finditer(line.text):
            country = match.group("country").strip(" .,:;-")
            if not country:
                continue
            candidates.append(
                CountryCandidate(
                    raw_value=country,
                    normalized_value=normalize_country(country),
                    source_line=line.text,
                    line_number=line.sequence_number,
                )
            )
    return candidates


def _text_candidate(raw_value: str, source_line: str, line_number: int) -> TextCandidate:
    return TextCandidate(
        raw_value=raw_value,
        normalized_value=normalize_text(raw_value),
        source_line=source_line,
        line_number=line_number,
    )


def _deduplicate_text(candidates: list[TextCandidate]) -> list[TextCandidate]:
    seen: set[tuple[str, int]] = set()
    unique: list[TextCandidate] = []
    for candidate in candidates:
        key = (candidate.normalized_value, candidate.line_number)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def _extract_abv_candidates(lines: list[OcrLine]) -> list[AbvCandidate]:
    candidates: list[AbvCandidate] = []
    seen: set[tuple[int, int, int]] = set()
    for line in lines:
        for pattern in ABV_PATTERNS:
            for match in pattern.finditer(line.text):
                key = (line.sequence_number, match.start(), match.end())
                if key in seen:
                    continue
                value = float(match.group("value"))
                if value <= 0 or value > 100:
                    continue
                seen.add(key)
                candidates.append(
                    AbvCandidate(
                        raw_value=match.group(0).strip(" ,;"),
                        normalized_percent=value,
                        source_line=line.text,
                        line_number=line.sequence_number,
                    )
                )
    return candidates


def _extract_volume_candidates(lines: list[OcrLine]) -> list[VolumeCandidate]:
    candidates: list[VolumeCandidate] = []
    for line in lines:
        for match in VOLUME_PATTERN.finditer(line.text):
            amount = float(match.group("value"))
            if amount <= 0:
                continue
            unit = match.group("unit").casefold()
            normalized_ml = amount * 1000 if unit == "l" or unit.startswith("lit") else amount
            candidates.append(
                VolumeCandidate(
                    raw_value=match.group(0).strip(),
                    normalized_ml=normalized_ml,
                    source_line=line.text,
                    line_number=line.sequence_number,
                )
            )
    return candidates


def _extract_class_type_candidates(lines: list[OcrLine]) -> list[TextCandidate]:
    candidates: list[TextCandidate] = []
    used: set[int] = set()
    for index, line in enumerate(lines):
        if index in used or not _is_class_line(line):
            continue
        coherent = [line]
        used.add(index)
        next_index = index + 1
        while next_index < len(lines):
            following = lines[next_index]
            if not _is_class_line(following) or not _lines_are_neighbors(coherent[-1], following):
                break
            coherent.append(following)
            used.add(next_index)
            next_index += 1
        raw_value = " ".join(candidate.text for candidate in coherent)
        normalized = normalize_text(raw_value)
        if normalized:
            candidates.append(
                TextCandidate(
                    raw_value=raw_value,
                    normalized_value=normalized,
                    source_line="\n".join(candidate.text for candidate in coherent),
                    line_number=coherent[0].sequence_number,
                )
            )
    return candidates


def _is_class_line(line: OcrLine) -> bool:
    return bool(CLASS_TYPE_CUES.search(line.text) and not EXCLUDED_BRAND_PHRASES.search(line.text))


def _lines_are_neighbors(first: OcrLine, second: OcrLine) -> bool:
    if first.bounding_box is None or second.bounding_box is None:
        return False
    if first.panel_id != second.panel_id:
        return False
    first_box = first.bounding_box
    second_box = second.bounding_box
    vertical_gap = second_box.top - (first_box.top + first_box.height)
    typical_height = max(
        first.approximate_line_height or first_box.height,
        second.approximate_line_height or second_box.height,
    )
    horizontal_tolerance = max(first_box.width, second_box.width) * 0.35
    return (
        -typical_height * 0.5 <= vertical_gap <= typical_height * 1.5
        and abs(first_box.left - second_box.left) <= horizontal_tolerance
    )


def _extract_brand_candidates(
    lines: list[OcrLine],
    *,
    producer_names: list[TextCandidate],
    producer_line_numbers: set[int],
    image_height: int | None,
) -> list[TextCandidate]:
    eligible: list[tuple[float, OcrLine]] = []
    panel_heights: dict[int, list[float]] = {}
    for line in lines:
        if line.approximate_line_height is not None:
            panel_heights.setdefault(line.panel_id, []).append(line.approximate_line_height)
    producer_values = {candidate.normalized_value for candidate in producer_names}
    for line in lines:
        normalized = normalize_text(line.text)
        if (
            not normalized
            or len(line.text) > 100
            or normalized in GENERIC_BRAND_LINES
            or CLASS_TYPE_CUES.search(line.text)
            or EXCLUDED_BRAND_PHRASES.search(line.text)
            or PRODUCER_CUE.search(line.text)
            or ORIGIN_PATTERN.search(line.text)
            or ADDRESS_CUE.search(line.text)
            or any(pattern.search(line.text) for pattern in ABV_PATTERNS)
            or VOLUME_PATTERN.search(line.text)
            or not any(character.isalpha() for character in line.text)
            or line.sequence_number in producer_line_numbers
        ):
            continue
        score = _brand_score(
            line,
            normalized=normalized,
            producer_values=producer_values,
            panel_heights=panel_heights,
            image_height=image_height,
        )
        eligible.append((score, line))
    if not eligible:
        return []
    eligible.sort(key=lambda item: (-item[0], item[1].sequence_number))
    if all(line.bounding_box is None for _score, line in eligible):
        selected = eligible[:3]
    else:
        best_score = eligible[0][0]
        selected = [item for item in eligible if item[0] >= best_score - 0.35][:3]
    return [
        _text_candidate(line.text, line.text, line.sequence_number) for _score, line in selected
    ]


def _brand_score(
    line: OcrLine,
    *,
    normalized: str,
    producer_values: set[str],
    panel_heights: dict[int, list[float]],
    image_height: int | None,
) -> float:
    score = max(0.0, 1.2 - line.sequence_number * 0.05)
    word_count = len(normalized.split())
    if 1 <= word_count <= 5:
        score += 0.5
    if normalized in producer_values:
        score += 2.0
    elif any(normalized in value or value in normalized for value in producer_values):
        score += 0.8
    if line.approximate_line_height is not None:
        typical = statistics.median(
            panel_heights.get(line.panel_id, [line.approximate_line_height])
        )
        score += min(2.5, line.approximate_line_height / max(typical, 1))
    if line.top is not None and image_height:
        relative_top = line.top / image_height
        if relative_top <= 0.35:
            score += 0.8
        elif relative_top > 0.7:
            score -= 0.6
    if line.mean_confidence is not None:
        score += line.mean_confidence * 0.4
    return score


def _plain_text_lines(raw_text: str) -> list[OcrLine]:
    return [
        OcrLine(
            text=" ".join(line.split()),
            words=(),
            bounding_box=None,
            mean_confidence=None,
            page_id=None,
            block_id=None,
            paragraph_id=None,
            line_id=None,
            approximate_line_height=None,
            sequence_number=number,
        )
        for number, line in enumerate(raw_text.splitlines(), 1)
        if line.strip()
    ]
