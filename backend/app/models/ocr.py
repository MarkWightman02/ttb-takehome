from typing import Literal

from pydantic import BaseModel, Field


class OcrImageMetadata(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    format: Literal["PNG", "JPEG", "WEBP"]


class LabelOcrResponse(BaseModel):
    raw_text: str
    engine: str
    processing_duration_ms: float = Field(ge=0)
    ocr_duration_ms: float = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    image: OcrImageMetadata
