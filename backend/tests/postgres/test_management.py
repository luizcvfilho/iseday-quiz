import csv
from io import BytesIO, StringIO

import pytest
from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AdminAuditLog

from .test_admin import admin as admin
from .test_admin import login
from .test_participants import WRITE, confirm, register, submit
from .test_participants import api as api

pytestmark = pytest.mark.postgres


HEADERS = [
    "Nome",
    "Escola",
    "Telefone",
    "E-mail",
    "Áreas vencedoras",
    "Cursos sugeridos",
    "Confirmação",
]


def read_export(response, format):
    if format == "csv":
        assert response.content.startswith(b"\xef\xbb\xbf")
        return list(csv.reader(StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
    assert response.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    workbook = load_workbook(BytesIO(response.content))
    sheet = workbook.active
    assert sheet.freeze_panes == "A2"
    assert all(cell.data_type != "f" for row in sheet for cell in row)
    rows = [[cell or "" for cell in row] for row in sheet.values]
    assert sheet.auto_filter.ref == f"A1:G{len(rows)}"
    workbook.close()
    return rows


@pytest.mark.parametrize("format", ["csv", "xlsx"])
@pytest.mark.parametrize("status", ["draft", "submitted"])
def test_export_includes_registration_results_and_pending_confirmation(api, admin, format, status):
    login(api)
    register(api, full_name='=HYPERLINK("example")')
    if status == "submitted":
        submit(api)
    response = api.client.get(f"/api/admin/export.{format}?status={status}")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.headers["content-disposition"] == (
        f'attachment; filename="participacoes-iseday.{format}"'
    )
    prefix = "'" if format == "csv" else ""
    assert read_export(response, format) == [
        HEADERS,
        [
            prefix + '=HYPERLINK("example")',
            "Test school",
            prefix + "+5511999999999",
            "student@example.org",
            "Area 0, Area 1" if status == "submitted" else "",
            "Course 0, Course 2" if status == "submitted" else "",
            "Sem resposta",
        ],
    ]
    empty = api.client.get(f"/api/admin/export.{format}?status=completed")
    assert read_export(empty, format) == [HEADERS]
    with Session(api.engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AdminAuditLog)
                .where(AdminAuditLog.action == "participations.export")
            )
            == 2
        )


@pytest.mark.parametrize("format", ["csv", "xlsx"])
@pytest.mark.parametrize("referral", ["all_courses", "chosen_course", "psychology"])
def test_export_contains_all_saved_winners_recommendations_and_confirmation(
    api, admin, format, referral
):
    login(api)
    register(api, school_name="Colégio São João")
    submit(api)
    result = confirm(
        api,
        agrees=referral != "psychology",
        course=api.quiz.courses[0] if referral == "chosen_course" else None,
    )
    assert result.status_code == 200
    response = api.client.get(f"/api/admin/export.{format}?status=completed")
    rows = read_export(response, format)
    assert rows[0] == HEADERS
    assert len(rows) == 2
    assert rows[1] == [
        "Test Student",
        "Colégio São João",
        ("'" if format == "csv" else "") + "+5511999999999",
        "student@example.org",
        "Area 0, Area 1",
        "Course 0, Course 2",
        "Discordou" if referral == "psychology" else "Concordou",
    ]


def test_export_requires_authentication_and_version_management_is_removed(api, admin):
    assert api.client.get("/api/admin/export.csv").status_code == 401
    assert api.client.get("/api/admin/export.xlsx").status_code == 401
    assert login(api).status_code == 200
    for path in (
        "versions",
        "versions/00000000-0000-0000-0000-000000000001",
        "versions/1/publish",
        "versions/1/archive",
    ):
        assert api.client.get(f"/api/admin/{path}").status_code == 404
        assert api.client.post(f"/api/admin/{path}", headers=WRITE, json={}).status_code == 404
    options = api.client.get("/api/admin/options").json()
    assert "versions" not in options
    assert all("quiz_version_id" not in item for item in options["courses"])
