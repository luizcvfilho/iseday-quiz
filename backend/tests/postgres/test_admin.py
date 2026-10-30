from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.admin.__main__ import save_account
from app.admin.security import cookie_name, passwords
from app.models import AdminAuditLog, AdminSession, AdminUser, Participation, QuizVersion
from app.participants.security import token_hash

from .test_participants import WRITE, confirm, register, submit
from .test_participants import api as api

pytestmark = pytest.mark.postgres
PASSWORD = "a sufficiently long test password"


@pytest.fixture
def admin(api):
    with Session(api.engine) as session, session.begin():
        save_account(session, "create", "admin@example.org", PASSWORD, "Equipe de teste")
        user_id = session.scalar(select(AdminUser.id))
    return user_id


def login(api, password=PASSWORD, email="admin@example.org", client=None):
    return (client or api.client).post(
        "/api/admin/login", headers=WRITE, json={"email": email, "password": password}
    )


def test_login_is_private_and_revocable(api, admin):
    registered = register(api).json()
    participant_cookie = api.client.cookies.get("iseday_participant")
    for path in (
        "me",
        "options",
        "summary",
        "participations",
        f"participations/{registered['id']}",
    ):
        assert api.client.get(f"/api/admin/{path}").status_code == 401
    assert login(api, "wrong").status_code == 401
    unknown = login(api, email="absent@example.org")
    assert unknown.status_code == 401
    assert unknown.json() == login(api, "wrong").json()
    result = login(api, email="ADMIN@example.org")
    assert result.status_code == 200, result.text
    assert result.json()["id"] == str(admin)
    assert set(result.json()) == {"id", "name", "email", "expires_at"}
    cookie = result.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/" in cookie
    assert result.headers["cache-control"] == "no-store"
    token = api.client.cookies.get("iseday_admin")
    with Session(api.engine) as session:
        credential = session.scalar(select(AdminSession))
        assert credential.token_hash == token_hash(token) and credential.token_hash != token
        assert passwords.verify(PASSWORD, session.get(AdminUser, admin).password_hash)
    assert api.client.get("/api/admin/me").status_code == 200
    assert api.client.cookies.get("iseday_participant") == participant_cookie
    assert api.client.post("/api/admin/logout", headers=WRITE).status_code == 204
    assert api.client.get("/api/participations/me").status_code == 200
    api.client.cookies.set("iseday_admin", token)
    assert api.client.get("/api/admin/me").status_code == 401
    assert api.client.post("/api/admin/logout", headers=WRITE).status_code == 204


def test_login_csrf_throttle_and_safe_validation(api, admin):
    body = {"email": "admin@example.org", "password": PASSWORD}
    assert api.client.post("/api/admin/login", json=body).status_code == 403
    assert (
        api.client.post(
            "/api/admin/login", json=body, headers={**WRITE, "Sec-Fetch-Site": "cross-site"}
        ).status_code
        == 403
    )
    invalid = api.client.post("/api/admin/login", headers=WRITE, json={**body, "extra": PASSWORD})
    assert invalid.status_code == 422 and PASSWORD not in invalid.text
    api.settings.admin_login_limit = 1
    assert login(api, "wrong").status_code == 401
    limited = api.client.post(
        "/api/admin/login", json=body, headers={**WRITE, "X-Forwarded-For": "192.0.2.1"}
    )
    assert limited.status_code == 429 and "retry-after" in limited.headers
    assert PASSWORD not in limited.text


@pytest.mark.parametrize("kind", ["expired", "revoked", "inactive", "malformed", "unknown"])
def test_rejects_invalid_sessions(api, admin, kind):
    assert login(api).status_code == 200
    with Session(api.engine) as session, session.begin():
        if kind == "expired":
            session.execute(
                update(AdminSession).values(
                    created_at=datetime.now(UTC) - timedelta(hours=2),
                    expires_at=datetime.now(UTC) - timedelta(hours=1),
                )
            )
        elif kind == "revoked":
            session.execute(update(AdminSession).values(revoked_at=datetime.now(UTC)))
        elif kind == "inactive":
            session.execute(update(AdminUser).values(is_active=False))
    if kind in ("malformed", "unknown"):
        api.client.cookies.clear()
        api.client.cookies.set("iseday_admin", "bad" if kind == "malformed" else token_urlsafe(32))
    assert api.client.get("/api/admin/participations").status_code == 401
    assert api.client.get(f"/api/admin/participations/{uuid4()}").status_code == 401
    if kind == "inactive":
        assert login(api).status_code == 401


def test_relogin_rotates_browser_session_and_reset_revokes_all_devices(api, admin):
    login(api)
    first = api.client.cookies.get("iseday_admin")
    login(api)
    assert first != api.client.cookies.get("iseday_admin")
    with TestClient(api.app) as other:
        other.cookies.set("iseday_admin", first)
        assert other.get("/api/admin/me").status_code == 401
        assert login(api, client=other).status_code == 200
        with Session(api.engine) as session, session.begin():
            save_account(session, "reset-password", "ADMIN@example.org", "a new long test password")
        assert other.get("/api/admin/me").status_code == 401
        assert api.client.get("/api/admin/me").status_code == 401
        assert login(api).status_code == 401
        assert login(api, password="a new long test password").status_code == 200
    with Session(api.engine) as session, session.begin():
        with pytest.raises(ValueError, match="Já existe"):
            save_account(session, "create", "ADMIN@example.org", PASSWORD, "Duplicate")


def make_participations(api):
    ids = []
    for name, state in (
        ("Ana Exemplo", "yes"),
        ("Bruno Exemplo", "no"),
        ("Carla Exemplo", "pending"),
        ("Daniel Rascunho", "draft"),
    ):
        ids.append(register(api, full_name=name).json()["id"])
        if state != "draft":
            assert submit(api).status_code == 200
        if state in ("yes", "no"):
            assert (
                confirm(
                    api,
                    agrees=state == "yes",
                    course=api.quiz.courses[0] if state == "yes" else None,
                ).status_code
                == 200
            )
        api.client.post("/api/participations/me/end", headers=WRITE)
    return ids


def test_list_details_summary_preserve_ties_and_drafts(api, admin):
    ids = make_participations(api)
    assert login(api).status_code == 200
    response = api.client.get("/api/admin/participations?page_size=2")
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["total"] == 4 and len(page["items"]) == 2
    assert [r["id"] for r in page["items"]] == ids[::-1][:2]
    assert "email" not in response.text and "phone" not in response.text
    next_page = api.client.get("/api/admin/participations?page=2&page_size=2").json()
    assert {row["id"] for row in page["items"]}.isdisjoint(row["id"] for row in next_page["items"])
    result = api.client.get(f"/api/admin/participations/{ids[0]}")
    assert result.status_code == 200, result.text
    detail = result.json()
    assert detail["email"] == api.payload["email"]
    assert len(detail["selections"]) == 25
    assert [s["display_order"] for s in detail["selections"]] == list(range(1, 26))
    assert len(detail["winning_areas"]) == 2 and len(detail["recommended_courses"]) == 2
    assert len(detail["result"]["areas"]) == 2 and len(detail["result"]["courses"]) == 3
    assert detail["result"]["feedback"]["chosen_course_id"] == str(api.quiz.courses[0])
    assert "access_token" not in result.text and "password" not in result.text
    assert result.headers["cache-control"] == "no-store"
    draft = api.client.get(f"/api/admin/participations/{ids[3]}").json()
    assert draft["result"] is None and draft["selections"] == []
    summary = api.client.get("/api/admin/summary").json()
    assert [summary[k] for k in ("total", "draft", "submitted", "completed")] == [4, 1, 1, 2]
    assert summary["agreed"] == summary["disagreed"] == 1 and summary["agreement_rate"] == 50
    assert [i["count"] for i in summary["areas"]] == [3, 3]
    assert [i["count"] for i in summary["courses"]] == [3, 3]
    assert summary["schools"][0]["count"] == 4
    assert api.client.get(f"/api/admin/participations/{uuid4()}").status_code == 404
    with Session(api.engine) as session:
        logs = session.scalars(select(AdminAuditLog)).all()
        assert any(
            log.action == "participations.view" and log.target_participation_id == UUID(ids[0])
            for log in logs
        )
        assert all(log.admin_user_id == admin for log in logs)


def test_filters_apply_equally_to_list_and_summary(api, admin):
    ids = make_participations(api)
    login(api)
    for params, expected in (
        ({"q": "aNA"}, [ids[0]]),
        ({"q": "%"}, []),
        ({"status": "completed"}, ids[:2]),
        ({"agreement": "yes"}, ids[:1]),
        ({"agreement": "no"}, ids[1:2]),
        ({"agreement": "pending"}, ids[2:]),
        ({"school_id": str(api.school)}, ids),
        ({"school_id": str(uuid4())}, []),
        ({"quiz_version_id": str(api.quiz.version)}, ids),
        ({"area_id": str(api.quiz.areas[0])}, ids[:3]),
        ({"course_id": str(api.quiz.courses[2])}, ids[:3]),
        ({"course_id": str(api.quiz.courses[1])}, []),
        ({"date_from": "2000-01-01", "date_to": "2000-01-01"}, []),
        ({"date_from": "2000-01-01", "date_to": "2099-01-01", "status": "submitted"}, ids[2:3]),
    ):
        response = api.client.get("/api/admin/participations", params=params)
        assert response.status_code == 200, response.text
        assert {p["id"] for p in response.json()["items"]} == set(expected), params
        response = api.client.get("/api/admin/summary", params=params)
        assert response.status_code == 200, response.text
        assert response.json()["total"] == len(expected), params
        if not expected:
            assert response.json()["agreement_rate"] is None
    for query in (
        "page=0",
        "page_size=101",
        "status=invalid",
        "date_from=2026-10-31&date_to=2026-10-01",
        "date_to=9999-12-31",
        "area_id=invalid",
    ):
        assert api.client.get(f"/api/admin/participations?{query}").status_code == 422


def test_archived_historical_result_and_options(api, admin):
    ids = make_participations(api)
    with api.engine.begin() as db:
        db.execute(update(QuizVersion).values(status="archived"))
    login(api)
    options = api.client.get("/api/admin/options").json()
    assert options["schools"][0]["id"] == str(api.school)
    assert options["versions"][0]["id"] == str(api.quiz.version)
    assert len(options["areas"]) == 2 and len(options["courses"]) == 3
    assert api.client.get(f"/api/admin/participations/{ids[0]}").json()["result"] is not None


def test_production_admin_cookie(api, admin):
    api.settings.app_env = "production"
    response = login(api)
    assert cookie_name(True) == "__Host-iseday_admin"
    assert "__Host-iseday_admin=" in response.headers["set-cookie"]
    assert "Secure" in response.headers["set-cookie"]
    assert "Domain=" not in response.headers["set-cookie"]
    with Session(api.engine) as session:
        assert session.scalar(select(func.count()).select_from(AdminSession)) == 1


def test_period_includes_whole_days_in_brasilia(api, admin):
    first = register(api).json()["id"]
    api.client.post("/api/participations/me/end", headers=WRITE)
    second = register(api).json()["id"]
    with Session(api.engine) as session, session.begin():
        for pid, stamp in (
            (first, "2026-01-02T02:59:59+00:00"),
            (second, "2026-01-02T03:00:00+00:00"),
        ):
            session.execute(
                update(Participation)
                .where(Participation.id == UUID(pid))
                .values(started_at=datetime.fromisoformat(stamp))
            )
    login(api)
    for day, expected in (("2026-01-01", first), ("2026-01-02", second)):
        query = {"date_from": day, "date_to": day}
        result = api.client.get("/api/admin/participations", params=query)
        assert [row["id"] for row in result.json()["items"]] == [expected]
        assert api.client.get("/api/admin/summary", params=query).json()["total"] == 1
