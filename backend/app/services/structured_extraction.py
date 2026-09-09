import re

from app.models.verification import (
    AbvCandidate,
    ExtractedCandidates,
    TextCandidate,
    VolumeCandidate,
)
from app.services.normalization import normalize_text

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
    r"(?P<unit>ml|millilit(?:er|re)s?|l|lit(?:er|re)s?)(?!\w)",
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
    r"imported\s+by|product\s+of|proof|net\s+contents?)\b",
    re.IGNORECASE,
)
GENERIC_BRAND_LINES = {
    "premium",
    "handcrafted",
    "small batch",
    "reserve",
    "established",
}


def extract_candidates(raw_text: str) -> ExtractedCandidates:
    lines = [
        (number, " ".join(line.split())) for number, line in enumerate(raw_text.splitlines(), 1)
    ]
    lines = [(number, line) for number, line in lines if line]
    return ExtractedCandidates(
        brand_name=_extract_brand_candidates(lines),
        class_type=_extract_class_type_candidates(lines),
        abv=_extract_abv_candidates(lines),
        net_contents=_extract_volume_candidates(lines),
    )


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
