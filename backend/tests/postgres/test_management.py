import csv
from io import StringIO

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AdminAuditLog

from .test_admin import admin as admin
from .test_admin import login
from .test_participants import WRITE, register, submit
from .test_participants import api as api

pytestmark = pytest.mark.postgres


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
    assert "Area 0 | Area 1" == rows[1][5]
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


def test_export_requires_authentication_and_version_management_is_removed(api, admin):
    assert api.client.get("/api/admin/export.csv").status_code == 401
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
