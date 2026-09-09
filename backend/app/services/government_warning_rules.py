"""Authoritative constants and physical tiers for the Government Health Warning.

Wording: 27 CFR 16.21. Presentation and physical tiers: 27 CFR 16.22.
Current TTB guidance also describes the statement as continuous:
https://www.ttb.gov/regulated-commodities/beverage-alcohol/beer/labeling/malt-beverage-health-warning
"""

from dataclasses import dataclass

# Prescribed by 27 CFR 16.21 (current eCFR):
# https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A/part-16/subpart-C/section-16.21
GOVERNMENT_WARNING_HEADING = "GOVERNMENT WARNING"
GOVERNMENT_WARNING_CLAUSE_ONE = (
    "(1) According to the Surgeon General, women should not drink alcoholic beverages "
    "during pregnancy because of the risk of birth defects."
)
GOVERNMENT_WARNING_CLAUSE_TWO = (
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)
PRESCRIBED_GOVERNMENT_WARNING = (
    f"{GOVERNMENT_WARNING_HEADING}: {GOVERNMENT_WARNING_CLAUSE_ONE} {GOVERNMENT_WARNING_CLAUSE_TWO}"
)


@dataclass(frozen=True, slots=True)
class PhysicalWarningRequirement:
    minimum_type_size_mm: int
    maximum_characters_per_inch: int


def physical_warning_requirement(volume_ml: float) -> PhysicalWarningRequirement:
    """Return the 27 CFR 16.22 type-size/CPI tier for container volume."""

    if volume_ml <= 237:
        return PhysicalWarningRequirement(1, 40)
    if volume_ml <= 3_000:
        return PhysicalWarningRequirement(2, 25)
    return PhysicalWarningRequirement(3, 12)
