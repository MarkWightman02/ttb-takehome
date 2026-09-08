from fastapi import APIRouter

from app.models.health import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Process liveness only; OCR readiness is not implemented."""
    return HealthResponse()
