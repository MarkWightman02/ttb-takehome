import logging

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_unexpected_errors_do_not_expose_submitted_content(
    settings: Settings, caplog: pytest.LogCaptureFixture
):
    app = create_app(settings)

    @app.get("/api/failure")
    async def failure():
        raise RuntimeError("private label content")

    with caplog.at_level(logging.ERROR), TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/failure")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "private label content" not in response.text
    assert "private label content" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_validation_errors_do_not_echo_submitted_values(settings: Settings):
    app = create_app(settings)

    @app.get("/api/example")
    async def example(count: int):
        return {"count": count}

    with TestClient(app) as client:
        response = client.get("/api/example", params={"count": "private label content"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "private label content" not in response.text


def test_http_error_preserves_required_headers(settings: Settings):
    app = create_app(settings)

    @app.get("/api/example")
    async def example():
        raise HTTPException(503, "Temporarily unavailable.", headers={"Retry-After": "5"})

    with TestClient(app) as client:
        response = client.get("/api/example")

    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    assert response.json()["error"]["message"] == "Temporarily unavailable."
