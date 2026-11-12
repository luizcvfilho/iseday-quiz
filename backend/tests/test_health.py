from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.db import get_session
from app.main import create_app


@pytest.fixture
def client():
    # Banco ficticio: testes nunca abrem conexao com o banco de desenvolvimento.
    app = create_app(
        Settings(
            app_env="test",
            database_url="mysql+pymysql://test:test@127.0.0.1:1/iseday_test",
            _env_file=None,
        )
    )
    session = Mock()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as test_client:
        yield test_client, session


def test_health_does_not_require_database(client):
    test_client, session = client
    response = test_client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    session.execute.assert_not_called()


def test_ready_checks_database(client):
    test_client, session = client
    response = test_client.get("/api/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    session.execute.assert_called_once()


def test_ready_returns_503_without_exposing_connection_details(client):
    test_client, session = client
    session.execute.side_effect = OperationalError("SELECT 1", {}, Exception("secret"))
    response = test_client.get("/api/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unavailable"}
    assert response.headers["cache-control"] == "no-store"
    assert "secret" not in response.text
