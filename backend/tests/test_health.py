from fastapi.testclient import TestClient


def test_health_returns_typed_liveness(client: TestClient):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok", "service": "ttb-label-verification"}


def test_unknown_api_route_has_json_error(client: TestClient):
    response = client.get("/api/verification")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Not Found"}}


def test_local_development_cors(client: TestClient):
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_unconfigured_origin_is_not_allowed(client: TestClient):
    response = client.get("/api/health", headers={"Origin": "https://unconfigured.example"})

    assert "access-control-allow-origin" not in response.headers
