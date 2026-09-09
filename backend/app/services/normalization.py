import re
import unicodedata
from decimal import Decimal, InvalidOperation

APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "`": "'", "´": "'"})
VOLUME_PATTERN = re.compile(
    r"^\s*(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>ml|millilit(?:er|re)s?|l|lit(?:er|re)s?)\s*$",
    re.IGNORECASE,
)


def normalize_text(value: str) -> str:
    """Normalize harmless typography without removing substantive words."""

    normalized = unicodedata.normalize("NFKC", value).translate(APOSTROPHES).casefold()
    normalized = normalized.replace("'", "")
    normalized = re.sub(r"[_\W]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


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
        raise ValueError("Net contents must use milliliters or liters, such as 750 mL or 1 L.")
    amount = Decimal(match.group("value"))
    if amount <= 0:
        raise ValueError("Net contents must be greater than zero.")
    unit = match.group("unit").casefold()
    if unit == "l" or unit.startswith("lit"):
        amount *= 1000
    return float(amount)
