import re

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
    r"product\s+of|made\s+in|proof|net\s+contents?|surgeon\s+general|"
    r"risk\s+of\s+birth\s+defects|consumption\s+of\s+alcoholic\s+beverages|"
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
    r"\b(?:product\s+of|imported\s+from|made\s+in)\s+"
    r"(?P<country>[A-Za-z][A-Za-z '-]{1,60}?)"
    r"(?=\s*(?:[.,;:]|(?:imported|bottled|produced)\s+by\b|$))",
    re.IGNORECASE,
)
ADDRESS_CUE = re.compile(
    r"(?:\b\d{5}(?:-\d{4})?\b|\b(?:street|st\.?|road|rd\.?|avenue|ave\.?|"
    r"boulevard|blvd\.?|lane|ln\.?|drive|dr\.?|highway|hwy\.?|p\.?\s*o\.?\s*box)\b|"
    rf"[A-Za-z .'-]+,?\s+[A-Z]{{2}}(?:\s+\d{{5}})?\s*$|"
    rf",\s*(?:{'|'.join(STATE_NAMES)})\s*$)",
    re.IGNORECASE,
)


def extract_candidates(raw_text: str) -> ExtractedCandidates:
    lines = [
        (number, " ".join(line.split())) for number, line in enumerate(raw_text.splitlines(), 1)
    ]
    lines = [(number, line) for number, line in lines if line]
    producer_names, producer_addresses = _extract_producer_candidates(lines)
    return ExtractedCandidates(
        brand_name=_extract_brand_candidates(lines),
        class_type=_extract_class_type_candidates(lines),
        abv=_extract_abv_candidates(lines),
        net_contents=_extract_volume_candidates(lines),
        producer_name=producer_names,
        producer_address=producer_addresses,
        country_origin=_extract_country_candidates(lines),
    )


def _extract_producer_candidates(
    lines: list[tuple[int, str]],
) -> tuple[list[TextCandidate], list[TextCandidate]]:
    names: list[TextCandidate] = []
    addresses: list[TextCandidate] = []
    for index, (line_number, line) in enumerate(lines):
        match = PRODUCER_CUE.search(line)
        if match is None:
            continue
        inline_name = match.group("name").strip(" ,:-")
        next_index = index + 1
        if inline_name:
            names.append(_text_candidate(inline_name, line, line_number))
        elif next_index < len(lines) and not ADDRESS_CUE.search(lines[next_index][1]):
            name_number, name_line = lines[next_index]
            names.append(_text_candidate(name_line, f"{line}\n{name_line}", name_number))
            next_index += 1
        for candidate_number, candidate_line in lines[next_index : next_index + 2]:
            if ADDRESS_CUE.search(candidate_line):
                addresses.append(
                    TextCandidate(
                        raw_value=candidate_line,
                        normalized_value=normalize_address(candidate_line),
                        source_line=candidate_line,
                        line_number=candidate_number,
                    )
                )
                break
    return _deduplicate_text(names), _deduplicate_text(addresses)


def _extract_country_candidates(lines: list[tuple[int, str]]) -> list[CountryCandidate]:
    candidates: list[CountryCandidate] = []
    for line_number, line in lines:
        for match in ORIGIN_PATTERN.finditer(line):
            country = match.group("country").strip(" .,:;-")
            if not country:
                continue
            candidates.append(
                CountryCandidate(
                    raw_value=country,
                    normalized_value=normalize_country(country),
                    source_line=line,
                    line_number=line_number,
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


def _extract_abv_candidates(lines: list[tuple[int, str]]) -> list[AbvCandidate]:
    candidates: list[AbvCandidate] = []
    seen: set[tuple[int, int, int]] = set()
    for line_number, line in lines:
        for pattern in ABV_PATTERNS:
            for match in pattern.finditer(line):
                key = (line_number, match.start(), match.end())
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
                        source_line=line,
                        line_number=line_number,
                    )
                )
    return candidates


def _extract_volume_candidates(lines: list[tuple[int, str]]) -> list[VolumeCandidate]:
    candidates: list[VolumeCandidate] = []
    for line_number, line in lines:
        for match in VOLUME_PATTERN.finditer(line):
            amount = float(match.group("value"))
            if amount <= 0:
                continue
            unit = match.group("unit").casefold()
            normalized_ml = amount * 1000 if unit == "l" or unit.startswith("lit") else amount
            candidates.append(
                VolumeCandidate(
                    raw_value=match.group(0).strip(),
                    normalized_ml=normalized_ml,
                    source_line=line,
                    line_number=line_number,
                )
            )
    return candidates


def _extract_class_type_candidates(lines: list[tuple[int, str]]) -> list[TextCandidate]:
    candidates: list[TextCandidate] = []
    for line_number, line in lines:
        if not CLASS_TYPE_CUES.search(line) or EXCLUDED_BRAND_PHRASES.search(line):
            continue
        normalized = normalize_text(line)
        if normalized:
            candidates.append(
                TextCandidate(
                    raw_value=line,
                    normalized_value=normalized,
                    source_line=line,
                    line_number=line_number,
                )
            )
    return candidates


def _extract_brand_candidates(lines: list[tuple[int, str]]) -> list[TextCandidate]:
    candidates: list[TextCandidate] = []
    for line_number, line in lines[:8]:
        normalized = normalize_text(line)
        if (
            not normalized
            or len(line) > 100
            or normalized in GENERIC_BRAND_LINES
            or CLASS_TYPE_CUES.search(line)
            or EXCLUDED_BRAND_PHRASES.search(line)
            or any(pattern.search(line) for pattern in ABV_PATTERNS)
            or VOLUME_PATTERN.search(line)
            or sum(character.isdigit() for character in line) > max(2, len(line) // 4)
        ):
            continue
        candidates.append(
            TextCandidate(
                raw_value=line,
                normalized_value=normalized,
                source_line=line,
                line_number=line_number,
            )
        )
        if len(candidates) == 3:
            break
    return candidates
