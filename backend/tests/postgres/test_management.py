import csv
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.admin import management
from app.admin.management_schemas import NewVersion
from app.models import AdminAuditLog, QuizVersion, StatementCourseWeight

from .test_admin import admin as admin
from .test_admin import login
from .test_participants import WRITE, register, submit
from .test_participants import api as api

pytestmark = pytest.mark.postgres


def create(api, source=None):
    response = api.client.post(
        "/api/admin/versions",
        headers=WRITE,
        json={"event_name": "Evento revisado", "source_version_id": source},
    )
    assert response.status_code == 201, response.text
    return response.json()


def payload(version):
    return {
        **{
            k: version[k]
            for k in ("event_name", "psychology_destination", "psychology_instructions")
        },
        "expected_revision": version["revision"],
        "statements": [
            {
                "id": s["id"],
                "text": s["text"],
                "courses": [
                    {"course_id": c["course_id"], "weight": c["weight"]} for c in s["courses"]
                ],
            }
            for s in version["statements"]
        ],
        "areas": [
            {k: a[k] for k in ("id", "destination", "destination_instructions")}
            for a in version["areas"]
        ],
        "courses": [
            {k: c[k] for k in ("id", "destination", "destination_instructions")}
            for c in version["courses"]
        ],
    }


def publication(api, version, **changes):
    return api.client.post(
        f"/api/admin/versions/{version['id']}/publish",
        headers=WRITE,
        json={
            "reviewed": True,
            "expected_published_id": str(api.quiz.version),
            "expected_revision": version["revision"],
            **changes,
        },
    )


def test_management_requires_admin_and_csrf(api, admin):
    register(api)
    for path in ("versions", f"versions/{api.quiz.version}", "export.csv"):
        assert api.client.get(f"/api/admin/{path}").status_code == 401
    for path, data in (
        ("versions", {"event_name": "Event"}),
        (f"versions/{api.quiz.version}", {"event_name": "Event"}),
        (f"versions/{api.quiz.version}/archive", {}),
        (f"versions/{api.quiz.version}/publish", {}),
    ):
        assert api.client.post(f"/api/admin/{path}", json=data, headers=WRITE).status_code == 401
    assert login(api).status_code == 200
    for path, data in (
        ("versions", {"event_name": "Event"}),
        (f"versions/{api.quiz.version}/archive", {}),
    ):
        assert api.client.post(f"/api/admin/{path}", json=data).status_code == 403
        assert (
            api.client.post(
                f"/api/admin/{path}", json=data, headers={**WRITE, "Sec-Fetch-Site": "cross-site"}
            ).status_code
            == 403
        )


def test_create_clone_edit_publish_and_history(api, admin):
    login(api)
    assert register(api).status_code == 201
    original = api.client.get(f"/api/admin/versions/{api.quiz.version}").json()
    draft = create(api, str(api.quiz.version))
    assert draft["status"] == "draft" and draft["version_number"] == 2
    assert len(draft["statements"]) == len(original["statements"])
    assert {s["id"] for s in draft["statements"]}.isdisjoint(
        {s["id"] for s in original["statements"]}
    )
    assert [[(c["course"], c["weight"]) for c in s["courses"]] for s in draft["statements"]] == [
        [(c["course"], c["weight"]) for c in s["courses"]] for s in original["statements"]
    ]
    data = payload(draft)
    data["areas"][0]["destination"] = "Bloco B"
    data["areas"][0]["destination_instructions"] = "Procure a recepção no térreo."
    data["courses"][0]["destination"] = "Laboratório 2"
    data["courses"][0]["destination_instructions"] = "Segundo andar."
    response = api.client.post(f"/api/admin/versions/{draft['id']}", json=data, headers=WRITE)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["revision"] != draft["revision"]
    assert saved["areas"][0]["destination"] == "Bloco B"
    assert publication(api, draft).status_code == 409  # review of stale content
    assert publication(api, saved, reviewed=False).status_code == 422
    assert publication(api, saved, reviewed=1).status_code == 422
    assert publication(api, saved, expected_published_id=None).status_code == 409
    result = publication(api, saved)
    assert result.status_code == 200, result.text
    assert api.client.get("/api/quiz/current").json()["id"] == saved["id"]
    assert api.client.get(f"/api/admin/versions/{api.quiz.version}").json()["status"] == "archived"
    assert submit(api).status_code == 200  # participant started on the previous version
    assert api.client.get("/api/participations/me/result").json()["quiz_version_id"] == str(
        api.quiz.version
    )
    assert (
        api.client.post(
            f"/api/admin/versions/{saved['id']}", json=payload(result.json()), headers=WRITE
        ).status_code
        == 409
    )
    assert (
        api.client.post(
            f"/api/admin/versions/{saved['id']}/archive", json={}, headers=WRITE
        ).status_code
        == 200
    )
    assert api.client.get("/api/quiz/current").status_code == 503
    assert (
        api.client.post(
            f"/api/admin/versions/{saved['id']}/archive", json={}, headers=WRITE
        ).status_code
        == 409
    )
    with Session(api.engine) as session:
        actions = session.scalars(select(AdminAuditLog.action)).all()
        assert f"versions.publish:{saved['id']}" in actions
        assert f"versions.archive:{saved['id']}" in actions


def test_original_catalog_and_invalid_edits_are_atomic(api, admin):
    login(api)
    draft = create(api)
    assert draft["statement_count"] == 74
    assert len(draft["areas"]) == 5 and len(draft["courses"]) == 11
    data = payload(draft)
    data["areas"][0]["destination"] = "Must roll back"
    data["courses"][0]["id"] = str(uuid4())
    assert (
        api.client.post(f"/api/admin/versions/{draft['id']}", headers=WRITE, json=data).status_code
        == 422
    )
    assert api.client.get(f"/api/admin/versions/{draft['id']}").json() == draft
    data = payload(draft)
    data["courses"][0]["destination"] = "Unpaired"
    assert (
        api.client.post(f"/api/admin/versions/{draft['id']}", headers=WRITE, json=data).status_code
        == 422
    )
    data = payload(draft)
    data["areas"] = [data["areas"][0]] * len(data["areas"])
    assert (
        api.client.post(f"/api/admin/versions/{draft['id']}", headers=WRITE, json=data).status_code
        == 422
    )
    with Session(api.engine) as session, session.begin():
        session.execute(
            delete(StatementCourseWeight).where(
                StatementCourseWeight.quiz_version_id == UUID(draft["id"])
            )
        )
    broken = api.client.get(f"/api/admin/versions/{draft['id']}").json()
    assert publication(api, broken).status_code == 422
    assert api.client.get("/api/quiz/current").json()["id"] == str(api.quiz.version)


def test_stale_save_and_concurrent_creation(api, admin):
    login(api)
    draft = create(api, str(api.quiz.version))
    data = payload(draft)
    data["event_name"] = "First edit"
    assert (
        api.client.post(f"/api/admin/versions/{draft['id']}", headers=WRITE, json=data).status_code
        == 200
    )
    assert (
        api.client.post(
            f"/api/admin/versions/{draft['id']}", headers=WRITE, json=payload(draft)
        ).status_code
        == 409
    )

    def copy():
        with Session(api.engine) as session, session.begin():
            return management.create_version(
                session, NewVersion(event_name="Copy", source_version_id=api.quiz.version)
            ).version_number

    with ThreadPoolExecutor(max_workers=2) as pool:
        numbers = list(pool.map(lambda _: copy(), range(2)))
    assert sorted(numbers) == [3, 4]


def test_csv_uses_filters_preserves_ties_and_escapes_formulas(api, admin):
    login(api)
    register(api, full_name='=HYPERLINK("example")')
    submit(api)
    response = api.client.get("/api/admin/export.csv?status=submitted")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert "attachment" in response.headers["content-disposition"]
    assert response.content.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
    assert len(rows) == 2 and rows[1][1].startswith("'=")
    assert "Area 0 | Area 1" == rows[1][6]
    assert "student@example.org" not in response.text and "+5511999999999" not in response.text
    empty = api.client.get("/api/admin/export.csv?status=completed")
    assert len(list(csv.reader(StringIO(empty.content.decode("utf-8-sig")), delimiter=";"))) == 1
    with Session(api.engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AdminAuditLog)
                .where(AdminAuditLog.action == "participations.export")
            )
            == 2
        )


def test_two_publications_cannot_silently_replace_each_other(api, admin):
    login(api)
    drafts = [create(api, str(api.quiz.version)) for _ in range(2)]
    cookies = dict(api.client.cookies)

    def publish(draft):
        with TestClient(api.app, cookies=cookies) as client:
            return client.post(
                f"/api/admin/versions/{draft['id']}/publish",
                headers=WRITE,
                json={
                    "reviewed": True,
                    "expected_published_id": str(api.quiz.version),
                    "expected_revision": draft["revision"],
                },
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(publish, drafts))
    assert sorted(statuses) == [200, 409]
    with Session(api.engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(QuizVersion)
                .where(QuizVersion.status == "published")
            )
            == 1
        )


def test_question_edits_new_links_and_weights_affect_only_the_new_version(api, admin):
    login(api)
    original = api.client.get(f"/api/admin/versions/{api.quiz.version}").json()
    draft = create(api, str(api.quiz.version))
    courses = {c["name"]: c["id"] for c in draft["courses"]}
    data = payload(draft)
    data["statements"][0]["text"] = "Texto revisado para a primeira afirmativa."
    data["statements"][0]["courses"] = [
        {"course_id": courses["Course 0"], "weight": 4},
        {"course_id": courses["Course 2"], "weight": 1},
    ]
    data["statements"][1]["courses"].append({"course_id": courses["Course 1"], "weight": 7})
    data["statements"].append(
        {
            "text": "Nova afirmativa do painel.",
            "courses": [
                {"course_id": courses["Course 0"], "weight": 3},
                {"course_id": courses["Course 1"], "weight": 5},
                {"course_id": courses["Course 2"], "weight": 2},
            ],
        }
    )
    response = api.client.post(f"/api/admin/versions/{draft['id']}", headers=WRITE, json=data)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["statement_count"] == 27
    assert saved["statements"][-1]["number"] == 27
    assert saved["statements"][0]["id"] == draft["statements"][0]["id"]
    assert api.client.get(f"/api/admin/versions/{api.quiz.version}").json() == original
    assert publication(api, draft).status_code == 409
    assert publication(api, saved).status_code == 200
    current = api.client.get("/api/quiz/current").json()
    assert len(current["statements"]) == 27
    assert current["statements"][0]["text"] == data["statements"][0]["text"]
    assert "courses" not in current["statements"][0]
    assert register(api, quiz_version_id=saved["id"]).status_code == 201
    chosen = [UUID(s["id"]) for s in saved["statements"][:24] + saved["statements"][-1:]]
    result = submit(api, ids=chosen)
    assert result.status_code == 200, result.text
    assert {c["name"]: c["score"] for c in result.json()["courses"]} == {
        "Course 0": 30,
        "Course 1": 12,
        "Course 2": 26,
    }
    assert {a["score"] for a in result.json()["areas"]} == {25}
    assert (
        api.client.post(
            f"/api/admin/versions/{saved['id']}", headers=WRITE, json=payload(saved)
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "defect",
    [
        "empty",
        "duplicate_text",
        "foreign_statement",
        "missing_statement",
        "duplicate_statement",
        "foreign_course",
        "duplicate_course",
        "no_course",
        "zero",
        "negative",
        "fraction",
        "overflow",
        "boolean",
    ],
)
def test_invalid_question_changes_roll_back_the_whole_draft(api, admin, defect):
    login(api)
    draft = create(api, str(api.quiz.version))
    data = payload(draft)
    data["areas"][0]["destination"] = "This change must also roll back"
    first = data["statements"][0]
    if defect == "empty":
        first["text"] = "  "
    elif defect == "duplicate_text":
        data["statements"][1]["text"] = "  " + first["text"].upper() + "  "
    elif defect == "foreign_statement":
        first["id"] = str(api.quiz.statements[0])
    elif defect == "missing_statement":
        data["statements"].pop()
    elif defect == "duplicate_statement":
        data["statements"][1]["id"] = first["id"]
    elif defect == "foreign_course":
        first["courses"][0]["course_id"] = str(api.quiz.courses[0])
    elif defect == "duplicate_course":
        first["courses"].append(first["courses"][0].copy())
    elif defect == "no_course":
        first["courses"] = []
    else:
        first["courses"][0]["weight"] = {
            "zero": 0,
            "negative": -1,
            "fraction": 1.5,
            "overflow": 32768,
            "boolean": True,
        }[defect]
    response = api.client.post(f"/api/admin/versions/{draft['id']}", headers=WRITE, json=data)
    assert response.status_code == 422, response.text
    assert api.client.get(f"/api/admin/versions/{draft['id']}").json() == draft
