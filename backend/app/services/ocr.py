from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """Region in source-image pixels, measured from the top-left corner."""

    left: int
    top: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class TextRegion:
    text: str
    bounding_box: BoundingBox | None = None
    confidence: float | None = None  # 0–1 when supported by the engine.
    is_bold: bool | None = None  # Unknown is distinct from false; plain OCR cannot prove boldness.
    page_id: int | None = None
    block_id: int | None = None
    paragraph_id: int | None = None
    line_id: int | None = None
    word_id: int | None = None


@dataclass(frozen=True, slots=True)
class OcrResult:
    text: str  # Preserve original case/wording for deterministic warning checks.
    regions: tuple[TextRegion, ...]
    image_width: int
    image_height: int
    engine_name: str
    duration_ms: float
    warnings: tuple[str, ...] = ()


class OcrUnavailableError(RuntimeError):
    """The configured local OCR runtime cannot be started."""


class OcrProcessingError(RuntimeError):
    """The OCR runtime started but could not process the image."""


class OcrService(Protocol):
    """Extract evidence from one request-scoped, preprocessed image.

    Adapters must not retain image bytes. Extraction provides evidence, never a
    compliance decision; unknown style or confidence must remain explicit.
    """

    async def extract(self, image: bytes, *, media_type: str) -> OcrResult: ...


RegionalPageSegmentationMode = Literal[6, 7, 8, 11, 13]


@runtime_checkable
class RegionalOcrService(Protocol):
    """Optional capability for bounded OCR refinement of an already-selected crop."""

    async def extract_region(
        self,
        image: bytes,
        *,
        media_type: str,
        page_segmentation_mode: RegionalPageSegmentationMode,
    ) -> OcrResult: ...
