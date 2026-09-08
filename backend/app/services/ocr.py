from dataclasses import dataclass
from typing import Protocol


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


@dataclass(frozen=True, slots=True)
class OcrResult:
    text: str  # Preserve original case/wording for deterministic warning checks.
    regions: tuple[TextRegion, ...]
    image_width: int
    image_height: int
    engine_name: str


class OcrService(Protocol):
    """Extract evidence from one image without retaining its bytes.

    Future adapters must document supported formats and limits. CPU-bound engines
    must execute outside the event loop. Extraction provides evidence, never a
    compliance decision; unknown style/confidence must remain explicit.
    """

    async def extract(self, image: bytes, *, media_type: str) -> OcrResult: ...
