from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_built_frontend_preserves_api_and_missing_asset_errors(settings: Settings, tmp_path: Path):
    (tmp_path / "index.html").write_text("<h1>TTB Label Verification</h1>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('loaded');", encoding="utf-8")
    settings.frontend_dist = tmp_path

    with TestClient(create_app(settings)) as client:
        index = client.get("/")
        assert index.status_code == 200
        assert "text/html" in index.headers["content-type"]
        assert "TTB Label Verification" in index.text
        assert client.get("/assets/app.js").status_code == 200
        assert client.get("/api/health").json()["status"] == "ok"

        for path in ["/api/missing", "/assets/missing.js", "/unknown-page"]:
            response = client.get(path)
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "not_found"


def test_assets_cannot_traverse_outside_the_build(settings: Settings, tmp_path: Path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<h1>Prototype</h1>", encoding="utf-8")
    (dist / "assets").mkdir()
    (tmp_path / "private.txt").write_text("private content", encoding="utf-8")
    settings.frontend_dist = dist

    with TestClient(create_app(settings)) as client:
        response = client.get("/assets/%2e%2e/%2e%2e/private.txt")

    assert response.status_code == 404
    assert "private content" not in response.text


def test_explicit_missing_frontend_fails_fast(settings: Settings, tmp_path: Path):
    settings.frontend_dist = tmp_path / "missing"

    with pytest.raises(ValueError, match="TTB_FRONTEND_DIST"):
        create_app(settings)
