import re
import unicodedata
from decimal import Decimal, InvalidOperation

APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "`": "'", "´": "'"})
VOLUME_PATTERN = re.compile(
    r"^\s*(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>ml|millilit(?:er|re)s?|l|lit(?:er|re)s?|"
    r"pints?|pt|fl\.?\s*oz\.?|fluid\s+ounces?)\s*$",
    re.IGNORECASE,
)

MILLILITERS_PER_US_FLUID_OUNCE = Decimal("29.5735295625")
MILLILITERS_PER_US_PINT = Decimal("473.176473")

STATE_NAMES = {
    "alabama": "al",
    "alaska": "ak",
    "arizona": "az",
    "arkansas": "ar",
    "california": "ca",
    "colorado": "co",
    "connecticut": "ct",
    "delaware": "de",
    "florida": "fl",
    "georgia": "ga",
    "hawaii": "hi",
    "idaho": "id",
    "illinois": "il",
    "indiana": "in",
    "iowa": "ia",
    "kansas": "ks",
    "kentucky": "ky",
    "louisiana": "la",
    "maine": "me",
    "maryland": "md",
    "massachusetts": "ma",
    "michigan": "mi",
    "minnesota": "mn",
    "mississippi": "ms",
    "missouri": "mo",
    "montana": "mt",
    "nebraska": "ne",
    "nevada": "nv",
    "new hampshire": "nh",
    "new jersey": "nj",
    "new mexico": "nm",
    "new york": "ny",
    "north carolina": "nc",
    "north dakota": "nd",
    "ohio": "oh",
    "oklahoma": "ok",
    "oregon": "or",
    "pennsylvania": "pa",
    "rhode island": "ri",
    "south carolina": "sc",
    "south dakota": "sd",
    "tennessee": "tn",
    "texas": "tx",
    "utah": "ut",
    "vermont": "vt",
    "virginia": "va",
    "washington": "wa",
    "west virginia": "wv",
    "wisconsin": "wi",
    "wyoming": "wy",
    "district of columbia": "dc",
}
COUNTRY_ALIASES = {
    "u s": "united states",
    "u s a": "united states",
    "usa": "united states",
    "united states of america": "united states",
    "uk": "united kingdom",
    "u k": "united kingdom",
}


def normalize_text(value: str) -> str:
    """Normalize harmless typography without removing substantive words."""

    normalized = unicodedata.normalize("NFKC", value).translate(APOSTROPHES).casefold()
    normalized = normalized.replace("'", "")
    normalized = re.sub(r"[_\W]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


def normalize_address(value: str) -> str:
    """Normalize presentation differences while retaining address identity."""

    normalized = normalize_text(value)
    for state_name in sorted(STATE_NAMES, key=len, reverse=True):
        normalized = re.sub(rf"\b{re.escape(state_name)}\b", STATE_NAMES[state_name], normalized)
    return normalized


def normalize_country(value: str) -> str:
    normalized = normalize_text(value)
    return COUNTRY_ALIASES.get(normalized, normalized)


def normalize_abv(value: str | float | Decimal) -> float:
    raw = str(value).strip()
    if raw.endswith("%"):
        raw = raw[:-1].strip()
    try:
        normalized = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("ABV must be a numeric percentage.") from exc
    if not normalized.is_finite() or normalized <= 0 or normalized > 100:
        raise ValueError("ABV must be greater than 0 and no more than 100 percent.")
    return float(normalized)


def normalize_volume(value: str) -> float:
    match = VOLUME_PATTERN.fullmatch(unicodedata.normalize("NFKC", value))
    if match is None:
        raise ValueError("Net contents must use mL, L, US pint, or US fluid ounce units.")
    amount = Decimal(match.group("value"))
    if amount <= 0:
        raise ValueError("Net contents must be greater than zero.")
    unit = match.group("unit").casefold()
    if unit == "l" or unit.startswith("lit"):
        amount *= 1000
    elif unit.startswith("pint") or unit == "pt":
        amount *= MILLILITERS_PER_US_PINT
    elif unit.startswith("fl") or unit.startswith("fluid"):
        amount *= MILLILITERS_PER_US_FLUID_OUNCE
    return float(amount)
