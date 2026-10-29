import secrets
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.db import get_session
from app.main import create_app
from app.participants.schemas import Registration
from app.participants.security import PublicRateLimiter, token_hash
from app.participants.service import find_participation


@pytest.fixture
def client():
    app = create_app(
        Settings(
            app_env="test",
            database_url="postgresql+psycopg://test:test@127.0.0.1:1/api_test",
            _env_file=None,
        )
    )
    session = Mock()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        yield client, session


@pytest.mark.parametrize("token", [None, "", "guess", "x" * 10000, "é" * 43])
def test_malformed_session_never_queries_database(token):
    session = Mock()
    assert find_participation(session, token) is None
    session.scalar.assert_not_called()


def test_token_is_hashed_and_distinct():
    token = secrets.token_urlsafe(32)
    digest = token_hash(token)
    assert len(digest) == 64
    assert digest != token and digest != token_hash(secrets.token_urlsafe(32))


@pytest.mark.parametrize(
    "path", ["/participations", "/participations/me/submit", "/participations/me/end"]
)
def test_writes_require_custom_header_before_database_access(client, path):
    client, session = client
    response = client.post(f"/api{path}", json={})
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
    session.begin.assert_not_called()


def test_cross_site_requests_and_cors_preflight_are_rejected(client):
    client, session = client
    assert (
        client.post(
            "/api/participations/me/end",
            headers={
                "X-Quiz-Request": "1",
                "Sec-Fetch-Site": "cross-site",
            },
        ).status_code
        == 403
    )
    response = client.options(
        "/api/participations",
        headers={
            "Origin": "https://other.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-Quiz-Request",
        },
    )
    assert "access-control-allow-origin" not in response.headers
    session.begin.assert_not_called()


def test_validation_errors_do_not_echo_personal_inputs(client):
    client, session = client
    response = client.post(
        "/api/participations",
        headers={"X-Quiz-Request": "1"},
        json={
            "full_name": "private-name",
            "phone": "private-phone",
            "email": "private-email",
            "access_token": "private-token",
        },
    )
    assert response.status_code == 422
    assert "private-" not in response.text
    assert all(set(error) == {"loc", "msg", "type"} for error in response.json()["detail"])
    session.begin.assert_not_called()


def test_phone_requires_brazilian_country_code_and_area_code():
    data = dict(
        quiz_version_id="00000000-0000-0000-0000-000000000001",
        school_id="00000000-0000-0000-0000-000000000002",
        full_name=" Student ",
        phone="+5511999999999",
        email="student@example.org",
        privacy_notice_version="test",
    )
    assert Registration(**data).full_name == "Student"
    for invalid in ("11999999999", "+5501999999999", "+5511999", "+5511999999999\n"):
        with pytest.raises(ValidationError):
            Registration(**{**data, "phone": invalid})


def test_rate_limit_window_and_retry_after():
    now = [10.0]
    limiter = PublicRateLimiter(clock=lambda: now[0])
    limiter.check("register", "device", 2)
    limiter.check("register", "device", 2)
    with pytest.raises(HTTPException) as error:
        limiter.check("register", "device", 2)
    assert error.value.status_code == 429
    assert error.value.headers == {"Retry-After": "60"}
    limiter.check("submit", "device", 2)
    limiter.check("register", "other", 2)
    now[0] = 70
    limiter.check("register", "device", 2)


def test_rate_limit_cache_is_bounded():
    limiter = PublicRateLimiter(capacity=3)
    for index in range(100):
        limiter.check("register", str(index), 1)
    assert len(limiter._windows) == 3
