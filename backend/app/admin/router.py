import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.admin import management, management_schemas, security, service
from app.admin.schemas import (
    AdminIdentity,
    Filters,
    Login,
    Options,
    PageFilters,
    ParticipationDetail,
    ParticipationPage,
    Summary,
)
from app.db import get_session
from app.models import AdminSession, AdminUser
from app.participants.security import require_write_request, token_hash

router = APIRouter(prefix="/api/admin", tags=["admin"])
Database = Annotated[Session, Depends(get_session)]
WRITE = [Depends(require_write_request)]


def access_token(request: Request) -> str | None:
    return request.cookies.get(
        security.cookie_name(request.app.state.settings.app_env == "production")
    )


def identity(user: AdminUser, expires: datetime):
    return AdminIdentity(id=user.id, name=user.name, email=user.email, expires_at=expires)


@dataclass
class AdminAccess:
    session: Session
    user: AdminUser
    credential: AdminSession


def authorized(request: Request, session: Database):
    with session.begin():
        # Keep status, selections and aggregates consistent during concurrent submissions.
        session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        user, credential = security.authenticate(session, access_token(request))
        yield AdminAccess(session, user, credential)


Access = Annotated[AdminAccess, Depends(authorized, scope="function")]
ReportFilters = Annotated[Filters, Query()]


def write_authorized(request: Request, session: Database):
    # Writes use fresh snapshots after waiting for the catalog lock.
    try:
        with session.begin():
            user, credential = security.authenticate(session, access_token(request))
            yield AdminAccess(session, user, credential)
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) in ("40001", "40P01", "23505", "23514", "P0001"):
            raise HTTPException(
                409, "Os dados mudaram ou são inconsistentes. Atualize e tente novamente."
            ) from exc
        raise


WriteAccess = Annotated[AdminAccess, Depends(write_authorized, scope="function")]


@router.post("/login", response_model=AdminIdentity, dependencies=WRITE)
def login(data: Login, request: Request, response: Response, session: Database):
    settings = request.app.state.settings
    limiter = request.app.state.public_rate_limiter
    host = request.client.host if request.client else "unknown"
    limiter.check("admin_login_ip", host, settings.admin_login_limit)
    # Account limit spans IPs without storing email addresses in the limiter.
    email = str(data.email).lower()
    limiter.check(
        "admin_login_account",
        hashlib.sha256(email.encode()).hexdigest(),
        settings.admin_login_limit,
    )
    with session.begin():
        user, token, expires = security.login(
            session, email, data.password, settings.admin_session_minutes, access_token(request)
        )
        result = identity(user, expires)
    production = settings.app_env == "production"
    response.set_cookie(
        security.cookie_name(production),
        token,
        max_age=settings.admin_session_minutes * 60,
        expires=expires,
        path="/",
        secure=production,
        httponly=True,
        samesite="strict",
    )
    return result


@router.get("/me", response_model=AdminIdentity)
def me(access: Access):
    return identity(access.user, access.credential.expires_at)


@router.post("/logout", status_code=204, dependencies=WRITE)
def logout(request: Request, response: Response, session: Database):
    with session.begin():
        hashed = token_hash(access_token(request))
        if hashed:
            credential = session.scalar(
                select(AdminSession).where(AdminSession.token_hash == hashed).with_for_update()
            )
            if credential is not None and credential.revoked_at is None:
                credential.revoked_at = datetime.now(UTC)
                user = session.get(AdminUser, credential.admin_user_id)
                security.audit(session, user, "logout")
    production = request.app.state.settings.app_env == "production"
    response.delete_cookie(
        security.cookie_name(production),
        path="/",
        secure=production,
        httponly=True,
        samesite="strict",
    )


@router.get("/options", response_model=Options)
def options(access: Access):
    return service.options(access.session)


@router.get("/participations", response_model=ParticipationPage)
def participations(
    access: Access,
    filters: Annotated[PageFilters, Query()],
):
    result = service.participations(access.session, filters, filters.page, filters.page_size)
    security.audit(access.session, access.user, "participations.list")
    return result


@router.get("/participations/{participation_id}", response_model=ParticipationDetail)
def detail(participation_id: UUID, access: Access):
    result = service.detail(access.session, participation_id)
    security.audit(access.session, access.user, "participations.view", participation_id)
    return result


@router.get("/summary", response_model=Summary)
def summary(access: Access, filters: ReportFilters):
    result = service.summary(access.session, filters)
    security.audit(access.session, access.user, "summary.view")
    return result


@router.get("/versions", response_model=list[management_schemas.VersionItem])
def versions(access: Access):
    return management.versions(access.session)


@router.get("/versions/{version_id}", response_model=management_schemas.VersionDetail)
def version_detail(version_id: UUID, access: Access):
    return management.version_detail(access.session, version_id)


@router.post(
    "/versions",
    response_model=management_schemas.VersionDetail,
    status_code=201,
    dependencies=WRITE,
)
def create_version(data: management_schemas.NewVersion, access: WriteAccess):
    result = management.create_version(access.session, data)
    security.audit(access.session, access.user, f"versions.create:{result.id}")
    return result


@router.post(
    "/versions/{version_id}", response_model=management_schemas.VersionDetail, dependencies=WRITE
)
def update_version(version_id: UUID, data: management_schemas.VersionInput, access: WriteAccess):
    result = management.save_version(access.session, version_id, data)
    security.audit(access.session, access.user, f"versions.update:{version_id}")
    return result


@router.post(
    "/versions/{version_id}/publish",
    response_model=management_schemas.VersionDetail,
    dependencies=WRITE,
)
def publish_version(version_id: UUID, data: management_schemas.PublishVersion, access: WriteAccess):
    result = management.publish(access.session, version_id, data)
    security.audit(access.session, access.user, f"versions.publish:{version_id}")
    return result


@router.post(
    "/versions/{version_id}/archive",
    response_model=management_schemas.VersionDetail,
    dependencies=WRITE,
)
def archive_version(version_id: UUID, access: WriteAccess):
    result = management.archive(access.session, version_id)
    security.audit(access.session, access.user, f"versions.archive:{version_id}")
    return result


@router.get("/export.csv")
def export_csv(access: Access, filters: ReportFilters):
    content = management.export_csv(access.session, filters)
    security.audit(access.session, access.user, "participations.export")
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="participacoes-iseday.csv"'},
    )
