from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import event, func, insert, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db import get_session
from app.main import create_app
from app.models import (
    Participation,
    ParticipationAreaResult,
    ParticipationCourseResult,
    ParticipationSelection,
    QuizVersion,
    School,
)
from app.participants import service
from app.participants.security import token_hash
from app.scoring import ScoringConfigurationError

from .conftest import migration_config
from .helpers import catalog

pytestmark = pytest.mark.postgres
WRITE = {"X-Quiz-Request": "1"}


@pytest.fixture
def api(empty_database):
    engine = empty_database
    with engine.begin() as db:
        command.upgrade(migration_config(db), "head")
        quiz = catalog(db)
        school = db.scalar(insert(School).values(name="Test school").returning(School.id))
    settings = Settings(
        app_env="test",
        database_url="postgresql+psycopg://unused:unused@localhost/unused_test",
        privacy_notice_version="test-v1",
        privacy_notice_text="Test notice. Use fictional data.",
        _env_file=None,
    )
    app = create_app(settings)

    def database():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = database
    payload = dict(
        quiz_version_id=str(quiz.version),
        school_id=str(school),
        full_name="Test Student",
        phone="+5511999999999",
        email="student@example.org",
        privacy_notice_version="test-v1",
    )
    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client,
            engine=engine,
            app=app,
            quiz=quiz,
            school=school,
            payload=payload,
            settings=settings,
        )


def register(api, client=None, **changes):
    return (client or api.client).post(
        "/api/participations", headers=WRITE, json={**api.payload, **changes}
    )


def submit(api, client=None, ids=None):
    ids = api.quiz.statements[:25] if ids is None else ids
    return (client or api.client).post(
        "/api/participations/me/submit",
        headers=WRITE,
        json={"statement_ids": [str(value) for value in ids]},
    )


def counts(api):
    with api.engine.connect() as db:
        return [
            db.scalar(select(func.count()).select_from(model))
            for model in (
                ParticipationSelection,
                ParticipationAreaResult,
                ParticipationCourseResult,
            )
        ]


def test_public_quiz_and_schools_do_not_expose_weights(api):
    response = api.client.get("/api/quiz/current")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(api.quiz.version)
    assert body["required_selection_count"] == 25
    assert len(body["statements"]) == 26
    assert body["privacy_notice_version"] == "test-v1"
    assert [s["display_order"] for s in body["statements"]] == list(range(1, 27))
    assert all(set(s) == {"id", "display_order", "text"} for s in body["statements"])
    assert "course" not in response.text and "weight" not in response.text
    with api.engine.begin() as db:
        db.execute(insert(School).values(name="Inactive", is_active=False))
        db.execute(insert(School).values(name="School 100%"))
    assert len(api.client.get("/api/schools").json()) == 2
    assert len(api.client.get("/api/schools?q=TEST").json()) == 1
    assert len(api.client.get("/api/schools?q=%25").json()) == 1
    assert len(api.client.get("/api/schools?limit=1").json()) == 1
    assert api.client.get("/api/schools?limit=101").status_code == 422


def test_registration_sets_hashed_expiring_session_and_can_be_retried(api):
    response = register(api)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/" in cookie
    assert "expires=" in cookie and "Max-Age=" in cookie
    token = api.client.cookies.get("iseday_participant")
    assert token not in response.text
    with Session(api.engine) as session:
        participant = session.get(Participation, UUID(body["id"]))
        assert participant.access_token_hash == token_hash(token)
        assert participant.access_expires_at - participant.started_at == timedelta(hours=1)
        assert participant.privacy_notice_version == "test-v1"
    retry = register(api)
    assert retry.status_code == 200 and retry.json() == body
    assert register(api, full_name="Different student").status_code == 409
    assert api.client.get("/api/participations/me").json() == body
    assert api.client.get("/api/participations/me/result").status_code == 409


def test_production_uses_secure_host_cookie(api):
    api.settings.app_env = "production"
    with TestClient(api.app, base_url="https://testserver") as client:
        response = register(api, client)
        assert response.status_code == 201
        assert "__Host-iseday_participant=" in response.headers["set-cookie"]
        assert "Secure" in response.headers["set-cookie"]
        assert client.get("/api/participations/me").status_code == 200
        assert client.post("/api/participations/me/end", headers=WRITE).status_code == 204


@pytest.mark.parametrize(
    ("field", "value", "status"),
    [
        ("email", "invalid", 422),
        ("phone", "11999999999", 422),
        ("full_name", " ", 422),
        ("school_id", str(uuid4()), 422),
        ("quiz_version_id", str(uuid4()), 409),
        ("privacy_notice_version", "old-notice", 409),
        ("status", "submitted", 422),
    ],
)
def test_rejects_invalid_registration_without_creating_records(api, field, value, status):
    assert register(api, **{field: value}).status_code == status
    with api.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(Participation)) == 0


def test_rejects_inactive_school_and_missing_notice(api):
    with api.engine.begin() as db:
        db.execute(update(School).where(School.id == api.school).values(is_active=False))
    assert register(api).status_code == 422
    api.settings.privacy_notice_text = None
    assert register(api).status_code == 503
    assert api.client.get("/api/quiz/current").status_code == 503


def test_unpublished_quiz_is_unavailable(api):
    with api.engine.begin() as db:
        db.execute(update(QuizVersion).values(status="archived"))
    assert api.client.get("/api/quiz/current").status_code == 503
    assert register(api).status_code == 409


def test_submit_persists_complete_results_and_replays_identical_choices(api, monkeypatch):
    assert register(api).status_code == 201
    result = submit(api)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["status"] == "submitted"
    assert counts(api) == [25, 2, 3]
    assert all(area["is_winner"] and area["score"] == 25 for area in body["areas"])
    assert {c["name"]: (c["score"], c["is_recommended"]) for c in body["courses"]} == {
        "Course 0": (25, True),
        "Course 1": (1, False),
        "Course 2": (25, True),
    }
    # Persisted history is replayed, even if future calculation code changes.
    monkeypatch.setattr(service, "calculate_scores", lambda *args: pytest.fail("recalculated"))
    assert submit(api, ids=api.quiz.statements[:25][::-1]).json() == body
    assert api.client.get("/api/participations/me/result").json() == body
    assert submit(api, ids=api.quiz.statements[1:]).status_code == 409
    assert counts(api) == [25, 2, 3]
    assert "student@example.org" not in result.text


@pytest.mark.parametrize("kind", ["24", "26", "duplicate", "unknown", "foreign"])
def test_rejects_invalid_selections_without_partial_writes(api, kind):
    assert register(api).status_code == 201
    ids = list(api.quiz.statements[:25])
    if kind in {"24", "26"}:
        ids = api.quiz.statements[: int(kind)]
    elif kind == "duplicate":
        ids[-1] = ids[0]
    elif kind == "unknown":
        ids[-1] = uuid4()
    else:
        with api.engine.begin() as db:
            other = catalog(db, number=2, publish=False)
        ids[-1] = other.statements[0]
    assert submit(api, ids=ids).status_code == 422
    assert counts(api) == [0, 0, 0]
    assert api.client.get("/api/participations/me").json()["status"] == "draft"


def test_catalog_configuration_failure_returns_503_without_partial_writes(api, monkeypatch):
    register(api)

    def broken(*args):
        raise ScoringConfigurationError("sensitive-internals")

    monkeypatch.setattr(service, "load_scoring_catalog", broken)
    response = submit(api)
    assert response.status_code == 503 and "sensitive-internals" not in response.text
    assert counts(api) == [0, 0, 0]


def test_failure_after_selections_rolls_back_all_writes(api):
    register(api)

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO participation_area_results"):
            # A genuine database error after the selection INSERTs, with no detail leak.
            conn.exec_driver_sql("SELECT 1 / 0 /* private-database-detail */")

    event.listen(api.engine, "before_cursor_execute", fail)
    try:
        response = submit(api)
    finally:
        event.remove(api.engine, "before_cursor_execute", fail)
    assert response.status_code == 503
    assert "private-database-detail" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert counts(api) == [0, 0, 0]
    assert api.client.get("/api/participations/me").json()["status"] == "draft"
    assert submit(api).status_code == 200


def test_sessions_isolate_participants_and_ids_are_not_credentials(api):
    first = register(api).json()
    assert submit(api).status_code == 200
    with TestClient(api.app) as other:
        assert other.get("/api/participations/me/result").status_code == 401
        other.cookies.set("iseday_participant", first["id"])
        assert other.get("/api/participations/me/result").status_code == 401
        other.cookies.clear()
        second = register(api, other).json()
        assert second["id"] != first["id"]
        assert other.get("/api/participations/me/result").status_code == 409
        own = submit(api, other, ids=api.quiz.statements[1:]).json()
        assert own["participation_id"] == second["id"]
        assert (
            own["statement_ids"]
            != api.client.get("/api/participations/me/result").json()["statement_ids"]
        )
        assert other.get(f"/api/participations/{first['id']}").status_code == 404


def test_expiry_revocation_and_idempotent_end_preserve_history(api):
    first = register(api).json()
    submit(api)
    token = api.client.cookies.get("iseday_participant")
    assert api.client.post("/api/participations/me/end", headers=WRITE).status_code == 204
    assert api.client.post("/api/participations/me/end", headers=WRITE).status_code == 204
    api.client.cookies.set("iseday_participant", token)
    assert api.client.get("/api/participations/me/result").status_code == 401
    assert counts(api) == [25, 2, 3]
    second = register(api).json()
    with api.engine.begin() as db:
        db.execute(
            update(Participation)
            .where(Participation.id == UUID(second["id"]))
            .values(
                started_at=func.clock_timestamp() - timedelta(hours=2),
                access_expires_at=func.clock_timestamp() - timedelta(hours=1),
            )
        )
    assert api.client.get("/api/participations/me").status_code == 401
    assert submit(api).status_code == 401
    assert first["id"] != second["id"]


def test_existing_participation_can_submit_after_version_archival(api):
    register(api)
    with api.engine.begin() as db:
        db.execute(
            update(QuizVersion).where(QuizVersion.id == api.quiz.version).values(status="archived")
        )
        catalog(db, number=2)
    assert submit(api).status_code == 200
    assert api.client.get("/api/participations/me/result").json()["quiz_version_id"] == str(
        api.quiz.version
    )


def test_api_rate_limits_and_cannot_bypass_with_forwarded_header(api):
    api.settings.participant_registration_limit = 1
    assert register(api).status_code == 201
    response = api.client.post(
        "/api/participations", json=api.payload, headers={**WRITE, "X-Forwarded-For": "192.0.2.1"}
    )
    assert response.status_code == 429 and "retry-after" in response.headers
    api.settings.participant_submission_limit = 1
    assert submit(api).status_code == 200
    assert submit(api).status_code == 429


@pytest.mark.parametrize("different", [False, True])
def test_concurrent_submissions_persist_one_result(api, different):
    register(api)
    token = api.client.cookies.get("iseday_participant")
    barrier = Barrier(2)

    def send(ids):
        # Independent HTTP clients, Sessions and DB connections share one credential.
        with TestClient(api.app) as client:
            client.cookies.set("iseday_participant", token)
            barrier.wait(timeout=5)
            response = submit(api, client, ids=ids)
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as workers:
        a = workers.submit(send, api.quiz.statements[:25])
        b = workers.submit(
            send, api.quiz.statements[1:] if different else api.quiz.statements[:25][::-1]
        )
        responses = [a.result(timeout=15), b.result(timeout=15)]
    assert sorted(status for status, _ in responses) == ([200, 409] if different else [200, 200])
    if not different:
        assert responses[0][1] == responses[1][1]
    assert counts(api) == [25, 2, 3]
