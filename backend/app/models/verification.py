from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.models.ocr import OcrImageMetadata

VerificationStatus = Literal["match", "review", "mismatch", "not_found", "not_applicable"]
RefinementField = Literal["brand_name", "class_type", "net_contents"]
FieldName = Literal[
    "brand_name",
    "class_type",
    "abv",
    "net_contents",
    "producer_name",
    "producer_address",
    "country_origin",
]


class ApplicationData(BaseModel):
    brand_name: str = Field(min_length=1, max_length=200)
    class_type: str = Field(min_length=1, max_length=200)
    abv: float = Field(gt=0, le=100)
    net_contents: str = Field(min_length=1, max_length=100)
    producer_name: str = Field(min_length=1, max_length=200)
    producer_address: str = Field(min_length=1, max_length=300)
    imported_product: bool
    country_origin: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def require_imported_origin(self) -> Self:
        if self.imported_product and (
            self.country_origin is None or not self.country_origin.strip()
        ):
            raise ValueError("Country of origin is required for an imported product.")
        return self


class TextCandidate(BaseModel):
    raw_value: str
    normalized_value: str
    source_line: str
    line_number: int = Field(ge=1)


class AbvCandidate(BaseModel):
    raw_value: str
    normalized_percent: float = Field(ge=0, le=100)
    source_line: str
    line_number: int = Field(ge=1)


class VolumeCandidate(BaseModel):
    raw_value: str
    normalized_ml: float = Field(gt=0)
    source_line: str
    line_number: int = Field(ge=1)


class CountryCandidate(BaseModel):
    raw_value: str
    normalized_value: str
    source_line: str
    line_number: int = Field(ge=1)


class ExtractedCandidates(BaseModel):
    brand_name: list[TextCandidate] = Field(default_factory=list)
    class_type: list[TextCandidate] = Field(default_factory=list)
    abv: list[AbvCandidate] = Field(default_factory=list)
    net_contents: list[VolumeCandidate] = Field(default_factory=list)
    producer_name: list[TextCandidate] = Field(default_factory=list)
    producer_address: list[TextCandidate] = Field(default_factory=list)
    country_origin: list[CountryCandidate] = Field(default_factory=list)


class FieldVerificationResult(BaseModel):
    field: FieldName
    expected_raw: str
    extracted_raw: str | None
    expected_normalized: str | float | None
    extracted_normalized: str | float | None
    status: VerificationStatus
    explanation: str
    evidence: list[str] = Field(default_factory=list)
    similarity_score: float | None = Field(default=None, ge=0, le=1)


class VerificationResults(BaseModel):
    brand_name: FieldVerificationResult
    class_type: FieldVerificationResult
    abv: FieldVerificationResult
    net_contents: FieldVerificationResult
    producer_name: FieldVerificationResult
    producer_address: FieldVerificationResult
    country_origin: FieldVerificationResult


class WarningBoundingBox(BaseModel):
    left: int = Field(ge=0)
    top: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    coordinate_space: Literal["preprocessed_image"] = "preprocessed_image"


class WarningCheck(BaseModel):
    status: VerificationStatus
    explanation: str
    evidence: list[str] = Field(default_factory=list)
    measurements: dict[str, str | float | int | bool | None] = Field(default_factory=dict)


class GovernmentWarningChecks(BaseModel):
    presence: WarningCheck
    wording: WarningCheck
    heading_capitalization: WarningCheck
    heading_boldness: WarningCheck
    body_not_bold: WarningCheck
    continuous_statement: WarningCheck
    separation: WarningCheck
    legibility_contrast: WarningCheck
    type_size: WarningCheck
    characters_per_inch: WarningCheck


class GovernmentWarningAnalysis(BaseModel):
    overall_status: VerificationStatus
    localized_text: str | None
    source_lines: list[str] = Field(default_factory=list)
    bounding_box: WarningBoundingBox | None
    mean_ocr_confidence: float | None = Field(default=None, ge=0, le=1)
    analysis_duration_ms: float = Field(ge=0)
    checks: GovernmentWarningChecks


class RefinementBoundingBox(BaseModel):
    left: int = Field(ge=0)
    top: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    coordinate_space: Literal["preprocessed_image"] = "preprocessed_image"


class OcrRefinementEvidence(BaseModel):
    field: RefinementField
    trigger: str
    full_image_candidates: list[str] = Field(default_factory=list)
    refined_text: str
    selected: bool
    page_segmentation_mode: Literal[6, 7]
    mean_confidence: float | None = Field(default=None, ge=0, le=1)
    duration_ms: float = Field(ge=0)
    crop: RefinementBoundingBox


class LabelVerificationResponse(BaseModel):
    expected: ApplicationData
    candidates: ExtractedCandidates
    results: VerificationResults
    government_warning: GovernmentWarningAnalysis
    overall_summary: str
    raw_text: str
    engine: str
    total_verification_duration_ms: float = Field(ge=0)
    ocr_duration_ms: float = Field(ge=0)
    refinement_duration_ms: float = Field(ge=0)
    ocr_invocation_count: int = Field(ge=1, le=4)
    ocr_refinements: list[OcrRefinementEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    image: OcrImageMetadata
