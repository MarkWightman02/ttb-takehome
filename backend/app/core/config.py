from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve the repository .env consistently when started from backend/ or the root.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TTB_",
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    frontend_dist: Path | None = None
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    max_image_width: int = Field(default=12_000, gt=0)
    max_image_height: int = Field(default=12_000, gt=0)
    max_image_pixels: int = Field(default=40_000_000, gt=0)
    tesseract_command: str = "tesseract"
    tesseract_language: str = "eng"
    ocr_timeout_seconds: float = Field(default=5.0, gt=0, le=60)

    @field_validator("cors_origins")
    @classmethod
    def validate_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("CORS origins must be explicit HTTP(S) origins without a path.")
        return [origin.rstrip("/") for origin in origins]
