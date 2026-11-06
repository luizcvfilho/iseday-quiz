from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import delete, event, func, select, text, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db import get_session
from app.main import create_app
from app.models import (
    Course,
    Participation,
    ParticipationAreaResult,
    ParticipationCourseResult,
    ParticipationFeedback,
    ParticipationSelection,
    StatementCourseWeight,
)
from app.participants import service
from app.participants.security import token_hash
from app.scoring import ScoringConfigurationError

from .conftest import migration_config
from .helpers import catalog

pytestmark = pytest.mark.postgres
WRITE = {"X-Quiz-Request": "1"}


@pytest.fixture
def api(empty_database, request):
    engine = empty_database
    with engine.begin() as db:
        command.upgrade(migration_config(db), "head")
        quiz = catalog(db)
        options = getattr(request, "param", {})
        if "course_destination" in options:
            destination, instructions = options["course_destination"]
            db.execute(text("ALTER TABLE courses DISABLE TRIGGER USER"))
            db.execute(
                update(Course)
                .where(Course.id == quiz.courses[0])
                .values(
                    destination=destination,
                    destination_instructions=instructions,
                )
            )
            db.execute(text("ALTER TABLE courses ENABLE TRIGGER USER"))
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
        school_name="Test school",
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


def test_public_quiz_does_not_expose_weights(api):
    response = api.client.get("/api/quiz/current")
    assert response.status_code == 200
    body = response.json()
    assert body["required_selection_count"] == 25
    assert len(body["statements"]) == 26
    assert body["privacy_notice_version"] == "test-v1"
    assert [s["display_order"] for s in body["statements"]] == list(range(1, 27))
    assert all(set(s) == {"id", "display_order", "text"} for s in body["statements"])
    assert "course" not in response.text and "weight" not in response.text


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
        assert participant.school_name == "Test school"
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


@pytest.mark.parametrize("status", ["draft", "submitted", "completed"])
@pytest.mark.parametrize("contact", ["email", "phone", "both"])
def test_lookup_recognizes_contacts_without_starting_a_session_or_exposing_data(
    api, status, contact
):
    register(api)
    if status != "draft":
        submit(api)
    if status == "completed":
        confirm(api)
    contacts = {
        key: value
        for key, value in api.payload.items()
        if key in ({"email", "phone"} if contact == "both" else {contact})
    }
    if "email" in contacts:
        contacts["email"] = contacts["email"].upper()
    with TestClient(api.app) as other:
        response = other.post("/api/participations/lookup", headers=WRITE, json=contacts)
        assert response.status_code == 200
        assert response.json() == {
            "status": status,
            "matched_by": [key for key in ("email", "phone") if key in contacts],
        }
        assert "set-cookie" not in response.headers
        assert response.headers["cache-control"] == "no-store"
        assert other.get("/api/participations/me").status_code == 401


@pytest.mark.parametrize("status", ["draft", "submitted", "completed"])
@pytest.mark.parametrize("contact", ["email", "phone"])
def test_contact_recovery_renews_session_and_preserves_participation(api, status, contact):
    first = register(api).json()
    saved = submit(api).json() if status != "draft" else None
    if status == "completed":
        confirm(api, agrees=False)
        saved = api.client.get("/api/participations/me/result").json()
    old_token = api.client.cookies.get("iseday_participant")
    # Recovery must also work after expiration, without the original cookie.
    with api.engine.begin() as db:
        db.execute(
            update(Participation)
            .where(Participation.id == UUID(first["id"]))
            .values(access_expires_at=Participation.started_at + timedelta(microseconds=1))
        )
    with TestClient(api.app) as other:
        response = other.post(
            "/api/participations/resume", headers=WRITE, json={contact: api.payload[contact]}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["id"] == first["id"] and body["status"] == status
        assert body["access_expires_at"] > first["access_expires_at"]
        assert other.cookies.get("iseday_participant") != old_token
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "SameSite=strict" in response.headers["set-cookie"]
        assert other.get("/api/participations/me").json() == body
        if saved:
            assert other.get("/api/participations/me/result").json() == saved
        else:
            assert other.get("/api/participations/me/quiz").status_code == 200
    assert api.client.get("/api/participations/me").status_code == 401
    with api.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(Participation)) == 1


def test_contact_recognition_requires_explicit_choice_to_create_a_new_test(api):
    first = register(api).json()
    saved = submit(api).json()
    with TestClient(api.app) as other:
        assert register(api, other).status_code == 409
        assert other.get("/api/participations/me").status_code == 401
        new = register(api, other, start_new=True)
        assert new.status_code == 201
        assert new.json()["id"] != first["id"] and new.json()["status"] == "draft"
        assert register(api, other, start_new=True).json() == new.json()
        other.post("/api/participations/me/end", headers=WRITE)
        recovered = other.post(
            "/api/participations/resume", headers=WRITE, json={"email": api.payload["email"]}
        )
        assert recovered.json()["id"] == new.json()["id"]
    assert api.client.get("/api/participations/me/result").json() == saved
    with api.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(Participation)) == 2


@pytest.mark.parametrize("path", ["lookup", "resume"])
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"email": "invalid"},
        {"phone": "11999999999"},
        {"email": "student@example.org", "participation_id": str(uuid4())},
    ],
)
def test_contact_routes_reject_invalid_inputs_and_identifiers(api, path, payload):
    response = api.client.post(f"/api/participations/{path}", headers=WRITE, json=payload)
    assert response.status_code == 422


def test_unknown_contacts_do_not_create_sessions_and_lookup_is_rate_limited(api):
    contacts = {"email": "unknown@example.org"}
    response = api.client.post("/api/participations/lookup", headers=WRITE, json=contacts)
    assert response.status_code == 200 and response.json() is None
    assert (
        api.client.post("/api/participations/resume", headers=WRITE, json=contacts).status_code
        == 404
    )
    assert api.client.get("/api/participations/me").status_code == 401
    api.settings.participant_registration_limit = 1
    response = api.client.post("/api/participations/lookup", headers=WRITE, json=contacts)
    assert response.status_code == 429 and "retry-after" in response.headers


@pytest.mark.parametrize(
    ("field", "value", "status"),
    [
        ("email", "invalid", 422),
        ("phone", "11999999999", 422),
        ("full_name", " ", 422),
        ("school_name", " ", 422),
        ("school_name", "x" * 201, 422),
        ("school_name", None, 422),
        ("school_id", str(uuid4()), 422),
        ("privacy_notice_version", "old-notice", 409),
        ("status", "submitted", 422),
    ],
)
def test_rejects_invalid_registration_without_creating_records(api, field, value, status):
    assert register(api, **{field: value}).status_code == status
    with api.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(Participation)) == 0


def test_rejects_missing_notice(api):
    api.settings.privacy_notice_text = None
    assert register(api).status_code == 503
    assert api.client.get("/api/quiz/current").status_code == 503


def test_submit_persists_complete_results_and_replays_identical_choices(api, monkeypatch):
    assert register(api).status_code == 201
    result = submit(api)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["status"] == "submitted"
    assert counts(api) == [25, 2, 3]
    assert all(area["is_winner"] and area["score"] == 25 for area in body["areas"])
    assert {area["id"]: area["destination"] for area in body["areas"]} == {
        str(area_id): "Space" for area_id in api.quiz.areas
    }
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
        ids[-1] = uuid4()
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
        second = register(api, other, start_new=True).json()
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
    second = register(api, start_new=True).json()
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


def confirm(api, *, agrees=True, course=None, client=None, **extra):
    return (client or api.client).post(
        "/api/participations/me/feedback",
        headers=WRITE,
        json={
            "agrees_with_result": agrees,
            "chosen_course_id": str(course) if course is not None else None,
            **extra,
        },
    )


def feedback_count(api):
    with api.engine.connect() as db:
        return db.scalar(select(func.count()).select_from(ParticipationFeedback))


@pytest.mark.parametrize("course_index", [0, 2])
def test_feedback_accepts_any_recommended_course_and_preserves_scores(api, course_index):
    register(api)
    before = submit(api).json()
    assert before["feedback"] is None
    course = api.quiz.courses[course_index]
    response = confirm(api, course=course)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["participation_id"] == before["participation_id"]
    assert body["status"] == "completed" and body["agrees_with_result"] is True
    assert body["chosen_course_id"] == str(course)
    assert body["destination"] == f"Estande de Course {course_index} — Ginásio"
    assert body["destination_instructions"] == (
        f"Vá ao ginásio e visite o estande de Course {course_index} "
        "para conhecer o curso e conversar com a equipe."
    )
    assert datetime.fromisoformat(body["answered_at"]) >= datetime.fromisoformat(
        before["submitted_at"]
    )
    assert body["answered_at"] == body["completed_at"]
    assert response.headers["cache-control"] == "no-store"
    after = api.client.get("/api/participations/me/result").json()
    assert after["status"] == "completed" and after["feedback"] == body
    assert after["areas"] == before["areas"] and after["courses"] == before["courses"]
    assert after["submitted_at"] == before["submitted_at"]
    assert after["statement_ids"] == before["statement_ids"]
    assert api.client.get("/api/participations/me").json()["status"] == "completed"
    assert confirm(api, course=course).json() == body
    # Retrying the original submission after completion still returns the saved history.
    assert submit(api).json() == after
    assert feedback_count(api) == 1 and counts(api) == [25, 2, 3]
    with Session(api.engine) as session:
        persisted = session.get(ParticipationFeedback, UUID(body["participation_id"]))
        assert persisted.chosen_course_id == course and persisted.destination == body["destination"]
        participant = session.get(Participation, UUID(body["participation_id"]))
        assert participant.completed_at == persisted.answered_at


@pytest.mark.parametrize(
    "api",
    [
        {"course_destination": ("Laboratório de teste", "Siga para a sala de teste 2.")},
    ],
    indirect=True,
)
def test_feedback_uses_gym_instead_of_old_course_destination(api):
    register(api)
    submit(api)
    body = confirm(api, course=api.quiz.courses[0]).json()
    assert body["destination"] == "Estande de Course 0 — Ginásio"
    assert "Vá ao ginásio e visite o estande de Course 0" in body["destination_instructions"]
    assert confirm(api, course=api.quiz.courses[0]).json() == body


def test_agreement_without_course_refers_to_all_saved_recommendations(api):
    register(api)
    before = submit(api).json()
    response = api.client.post(
        "/api/participations/me/feedback", headers=WRITE, json={"agrees_with_result": True}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["chosen_course_id"] is None
    assert body["destination"] == "Estandes dos cursos indicados — Ginásio"
    assert body["destination_instructions"] == (
        "Vá ao ginásio e visite os estandes dos cursos indicados pelo quiz:\n• Course 0\n• Course 2"
    )
    assert confirm(api).json() == body
    after = api.client.get("/api/participations/me/result").json()
    assert after["feedback"] == body
    assert after["courses"] == before["courses"] and after["areas"] == before["areas"]
    assert feedback_count(api) == 1


def test_agreement_without_course_refers_to_the_single_recommendation(api):
    with api.engine.begin() as db:
        db.execute(text("ALTER TABLE statement_course_weights DISABLE TRIGGER USER"))
        db.execute(
            delete(StatementCourseWeight).where(
                StatementCourseWeight.course_id == api.quiz.courses[2]
            )
        )
        db.execute(text("ALTER TABLE statement_course_weights ENABLE TRIGGER USER"))
    register(api)
    submit(api)
    response = confirm(api)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["chosen_course_id"] is None
    assert body["destination"] == "Estande de Course 0 — Ginásio"
    assert body["destination_instructions"] == (
        "Vá ao ginásio e visite o estande de Course 0 "
        "para conhecer o curso e conversar com a equipe."
    )
    assert confirm(api).json() == body


def test_negative_feedback_uses_fixed_psychology_destination(api):
    register(api)
    submit(api)
    response = confirm(api, agrees=False)
    body = response.json()
    assert body["agrees_with_result"] is False and body["chosen_course_id"] is None
    assert body["destination"] == "Estande de Psicologia — Ginásio"
    assert body["destination_instructions"] == (
        "Vá ao ginásio e visite o estande de Psicologia para conversar com a equipe "
        "sobre seus interesses e explorar outras possibilidades."
    )
    assert confirm(api, agrees=False).json() == body
    api.settings.privacy_notice_text = None
    assert api.client.get("/api/participations/me/result").json()["feedback"] == body
    assert feedback_count(api) == 1


def test_feedback_can_be_revised_in_both_directions_without_changing_quiz_or_completion(api):
    register(api)
    before = submit(api).json()
    first = confirm(api).json()
    for agrees, course in [(False, None), (True, api.quiz.courses[2]), (True, None)]:
        response = confirm(api, agrees=agrees, course=course)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["agrees_with_result"] is agrees
        assert body["chosen_course_id"] == (str(course) if course else None)
        assert body["completed_at"] == first["completed_at"]
        assert body["answered_at"] > first["answered_at"]
        assert ("Psicologia" in body["destination"]) is (not agrees)
        assert confirm(api, agrees=agrees, course=course).json() == body
        after = api.client.get("/api/participations/me/result").json()
        assert after["feedback"] == body and after["status"] == "completed"
        for field in ("areas", "courses", "statement_ids", "submitted_at"):
            assert after[field] == before[field]
    assert feedback_count(api) == 1 and counts(api) == [25, 2, 3]


def test_feedback_revision_failure_preserves_previous_referral(api):
    register(api)
    submit(api)
    first = confirm(api).json()
    assert confirm(api, course=api.quiz.courses[1]).status_code == 422

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE participation_feedback SET"):
            conn.exec_driver_sql("SELECT 1 / 0 /* private-feedback-revision-failure */")

    event.listen(api.engine, "before_cursor_execute", fail)
    try:
        response = confirm(api, agrees=False)
    finally:
        event.remove(api.engine, "before_cursor_execute", fail)
    assert response.status_code == 503 and "private-feedback-revision-failure" not in response.text
    assert api.client.get("/api/participations/me/result").json()["feedback"] == first
    assert confirm(api, agrees=False).status_code == 200
    assert feedback_count(api) == 1


def test_feedback_revision_migration_unlocks_existing_completed_results(api):
    with api.engine.begin() as db:
        command.downgrade(migration_config(db), "0004")
    register(api)
    before = submit(api).json()
    first = confirm(api).json()
    # Reproduce a running API whose code reloaded before its database was migrated.
    assert confirm(api, agrees=False).status_code == 503
    assert api.client.get("/api/participations/me/result").json()["feedback"] == first

    with api.engine.begin() as db:
        command.upgrade(migration_config(db), "head")
    response = confirm(api, agrees=False)
    assert response.status_code == 200, response.text
    revised = response.json()
    assert revised["agrees_with_result"] is False
    assert revised["destination"] == "Estande de Psicologia — Ginásio"
    assert revised["completed_at"] == first["completed_at"]
    saved = api.client.get("/api/participations/me/result").json()
    assert saved["feedback"] == revised
    for field in ("areas", "courses", "statement_ids", "submitted_at"):
        assert saved[field] == before[field]
    assert feedback_count(api) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"agrees_with_result": True, "chosen_course_id": "invalid"},
        {"agrees_with_result": False, "chosen_course_id": str(uuid4())},
        {"agrees_with_result": "false"},
        {"agrees_with_result": 1},
        {"agrees_with_result": None},
        {"chosen_course_id": None},
        {"agrees_with_result": False, "destination": "Forged destination"},
    ],
)
def test_feedback_rejects_ambiguous_or_forged_payloads(api, payload):
    register(api)
    submit(api)
    response = api.client.post("/api/participations/me/feedback", headers=WRITE, json=payload)
    assert response.status_code == 422
    assert feedback_count(api) == 0
    assert api.client.get("/api/participations/me").json()["status"] == "submitted"


@pytest.mark.parametrize("kind", ["not_recommended", "unknown", "foreign"])
def test_feedback_rejects_courses_outside_saved_recommendations(api, kind):
    register(api)
    submit(api)
    course = api.quiz.courses[1] if kind == "not_recommended" else uuid4()
    if kind == "foreign":
        course = uuid4()
    response = confirm(api, course=course)
    assert response.status_code == 422
    assert feedback_count(api) == 0
    assert api.client.get("/api/participations/me").json()["status"] == "submitted"


def test_feedback_requires_submission_and_valid_session(api):
    assert confirm(api, agrees=False).status_code == 401
    registered = register(api).json()
    assert confirm(api, agrees=False).status_code == 409
    submit(api)
    with api.engine.begin() as db:
        db.execute(
            update(Participation)
            .where(Participation.id == UUID(registered["id"]))
            .values(
                access_expires_at=Participation.started_at + timedelta(microseconds=1),
            )
        )
    assert confirm(api, agrees=False).status_code == 401
    api.client.post("/api/participations/me/end", headers=WRITE)
    assert confirm(api, agrees=False).status_code == 401
    assert feedback_count(api) == 0


def test_feedback_rollback_after_insert_preserves_submitted_state(api):
    register(api)
    submit(api)

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE participations SET") and "completed_at" in statement:
            conn.exec_driver_sql("SELECT 1 / 0 /* private-feedback-failure */")

    event.listen(api.engine, "before_cursor_execute", fail)
    try:
        response = confirm(api, agrees=False)
    finally:
        event.remove(api.engine, "before_cursor_execute", fail)
    assert response.status_code == 503 and "private-feedback-failure" not in response.text
    assert feedback_count(api) == 0
    assert api.client.get("/api/participations/me").json()["status"] == "submitted"
    assert api.client.get("/api/participations/me/result").json()["feedback"] is None
    assert confirm(api, agrees=False).status_code == 200


def test_feedback_is_private_and_end_keeps_completed_history(api):
    registered = register(api).json()
    submit(api)
    first = confirm(api, course=api.quiz.courses[0]).json()
    with TestClient(api.app) as other:
        assert confirm(api, agrees=False, client=other).status_code == 401
        second = register(api, other, start_new=True).json()
        submit(api, other)
        assert (
            confirm(api, agrees=False, client=other, participation_id=registered["id"]).status_code
            == 422
        )
        own = confirm(api, agrees=False, client=other).json()
        assert own["participation_id"] == second["id"] != first["participation_id"]
        assert own["destination"] == "Estande de Psicologia — Ginásio"
        assert api.client.get("/api/participations/me/result").json()["feedback"] == first
    token = api.client.cookies.get("iseday_participant")
    assert api.client.post("/api/participations/me/end", headers=WRITE).status_code == 204
    api.client.cookies.set("iseday_participant", token)
    assert confirm(api, course=api.quiz.courses[0]).status_code == 401
    assert api.client.get("/api/participations/me/result").status_code == 401
    assert feedback_count(api) == 2
    with Session(api.engine) as session:
        assert session.get(Participation, UUID(registered["id"])).status == "completed"


def test_feedback_has_its_own_rate_limit_window(api):
    register(api)
    api.settings.participant_submission_limit = 1
    assert submit(api).status_code == 200
    assert confirm(api, agrees=False).status_code == 200
    response = confirm(api, agrees=False)
    assert response.status_code == 429 and "retry-after" in response.headers
    assert feedback_count(api) == 1


@pytest.mark.parametrize("different", ["identical", "agreement", "course"])
def test_concurrent_feedback_persists_one_confirmation(api, different):
    register(api)
    submit(api)
    token = api.client.cookies.get("iseday_participant")
    barrier = Barrier(2)

    def send(agrees, course):
        with TestClient(api.app) as client:
            client.cookies.set("iseday_participant", token)
            barrier.wait(timeout=5)
            response = confirm(api, client=client, agrees=agrees, course=course)
            return response.status_code, response.json()

    agrees = different != "agreement"
    course = api.quiz.courses[2] if different == "course" else api.quiz.courses[0]
    with ThreadPoolExecutor(max_workers=2) as workers:
        a = workers.submit(send, True, api.quiz.courses[0])
        b = workers.submit(send, agrees, course if agrees else None)
        responses = [a.result(timeout=15), b.result(timeout=15)]
    assert [status for status, _ in responses] == [200, 200]
    saved = api.client.get("/api/participations/me/result").json()
    assert saved["status"] == "completed"
    assert saved["feedback"] in [body for _, body in responses]
    if different == "identical":
        assert responses[0][1] == responses[1][1]
    assert feedback_count(api) == 1 and counts(api) == [25, 2, 3]


def test_free_text_school_is_trimmed_saved_and_used_for_registration_retries(api):
    response = register(api, school_name="  Colégio Livre São João  ")
    assert response.status_code == 201
    with Session(api.engine) as session:
        participant = session.get(Participation, UUID(response.json()["id"]))
        assert participant.school_name == "Colégio Livre São João"
    assert register(api, school_name="Colégio Livre São João").status_code == 200
    assert register(api, school_name="Outra escola").status_code == 409
    payload = {key: value for key, value in api.payload.items() if key != "school_name"}
    assert api.client.post("/api/participations", headers=WRITE, json=payload).status_code == 422
    assert api.client.get("/api/schools").status_code == 404
