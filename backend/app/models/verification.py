from typing import Literal

from pydantic import BaseModel, Field

from app.models.ocr import OcrImageMetadata

VerificationStatus = Literal["match", "review", "mismatch", "not_found"]
FieldName = Literal["brand_name", "class_type", "abv", "net_contents"]


class ApplicationData(BaseModel):
    brand_name: str = Field(min_length=1, max_length=200)
    class_type: str = Field(min_length=1, max_length=200)
    abv: float = Field(gt=0, le=100)
    net_contents: str = Field(min_length=1, max_length=100)


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


class ExtractedCandidates(BaseModel):
    brand_name: list[TextCandidate] = Field(default_factory=list)
    class_type: list[TextCandidate] = Field(default_factory=list)
    abv: list[AbvCandidate] = Field(default_factory=list)
    net_contents: list[VolumeCandidate] = Field(default_factory=list)


class FieldVerificationResult(BaseModel):
    field: FieldName
    expected_raw: str
    extracted_raw: str | None
    expected_normalized: str | float
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


class LabelVerificationResponse(BaseModel):
    expected: ApplicationData
    candidates: ExtractedCandidates
    results: VerificationResults
    overall_summary: str
    raw_text: str
    engine: str
    total_verification_duration_ms: float = Field(ge=0)
    ocr_duration_ms: float = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    image: OcrImageMetadata
