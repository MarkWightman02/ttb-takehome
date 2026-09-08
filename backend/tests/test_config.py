import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_read_prefixed_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TTB_ENVIRONMENT", "production")
    monkeypatch.setenv("TTB_CORS_ORIGINS", '["https://prototype.example"]')

    settings = Settings(_env_file=None)

    assert settings.environment == "production"
    assert settings.cors_origins == ["https://prototype.example"]


def test_invalid_settings_are_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="invalid")

    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_origins=["*"])
