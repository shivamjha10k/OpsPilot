from fastapi.testclient import TestClient

from app.core.errors import AppError
from app.main import app


def test_auth_routes_are_registered() -> None:
    paths = {route.path for route in app.routes}

    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/refresh" in paths
    assert "/api/v1/auth/logout" in paths
    assert "/api/v1/auth/me" in paths


def test_me_requires_bearer_authentication() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_production_settings_reject_default_secret() -> None:
    from app.core.config import Settings

    try:
        Settings(environment="production")
    except ValueError as exc:
        assert "JWT_SECRET" in str(exc)
    else:
        raise AssertionError("weak production JWT secret was accepted")
