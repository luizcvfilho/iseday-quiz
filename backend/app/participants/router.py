from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import School
from app.participants import service
from app.participants.schemas import (
    CurrentQuiz,
    ParticipationResult,
    ParticipationSession,
    PublicSchool,
    Registration,
    Submission,
)
from app.participants.security import cookie_name, require_write_request, token_hash

router = APIRouter(prefix="/api", tags=["participant"])
Database = Annotated[Session, Depends(get_session)]
WRITE = [Depends(require_write_request)]


def access_token(request: Request) -> str | None:
    return request.cookies.get(cookie_name(request.app.state.settings.app_env == "production"))


def throttle(request: Request, action: str, limit: int) -> None:
    # Do not trust arbitrary X-Forwarded-For headers. Configure trusted proxies at Uvicorn.
    host = request.client.host if request.client else "unknown"
    request.app.state.public_rate_limiter.check(action, host, limit)


@router.get("/quiz/current", response_model=CurrentQuiz)
def quiz(request: Request, session: Database):
    with session.begin():
        return service.current_quiz(session, request.app.state.settings)


@router.get("/schools", response_model=list[PublicSchool])
def schools(
    session: Database,
    q: Annotated[str, Query(max_length=100)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    query = select(School).where(School.is_active.is_(True))
    if q.strip():
        query = query.where(School.name.icontains(q.strip(), autoescape=True))
    with session.begin():
        return [
            PublicSchool(id=s.id, name=s.name, city=s.city, state_code=s.state_code)
            for s in session.scalars(query.order_by(School.name, School.id).limit(limit))
        ]


@router.post("/participations", response_model=ParticipationSession, dependencies=WRITE)
def register(data: Registration, request: Request, response: Response, session: Database):
    settings = request.app.state.settings
    throttle(request, "registration", settings.participant_registration_limit)
    with session.begin():
        summary, token, created = service.register(session, data, settings, access_token(request))
    response.status_code = 201 if created else 200
    production = settings.app_env == "production"
    response.set_cookie(
        cookie_name(production),
        token,
        max_age=max(0, int((summary.access_expires_at - datetime.now(UTC)).total_seconds())),
        expires=summary.access_expires_at.astimezone(UTC),
        path="/",
        secure=production,
        httponly=True,
        samesite="strict",
    )
    return summary


@router.get("/participations/me", response_model=ParticipationSession)
def me(request: Request, session: Database):
    with session.begin():
        return service.session_summary(
            service.authenticated_participation(session, access_token(request))
        )


@router.post("/participations/me/submit", response_model=ParticipationResult, dependencies=WRITE)
def submit(data: Submission, request: Request, session: Database):
    settings = request.app.state.settings
    throttle(request, "submission", settings.participant_submission_limit)
    hashed = token_hash(access_token(request))
    if hashed:
        request.app.state.public_rate_limiter.check("participant_submission", hashed, 30)
    with session.begin():
        participant = service.authenticated_participation(session, access_token(request))
        return service.submit(session, participant, data.statement_ids)


@router.get("/participations/me/result", response_model=ParticipationResult)
def result(request: Request, session: Database):
    with session.begin():
        return service.saved_result(
            session, service.authenticated_participation(session, access_token(request))
        )


@router.post("/participations/me/end", status_code=204, dependencies=WRITE)
def end(request: Request, response: Response, session: Database):
    with session.begin():
        participant = service.find_participation(session, access_token(request))
        if participant:
            participant.access_token_hash = None
            session.flush()
    production = request.app.state.settings.app_env == "production"
    response.delete_cookie(
        cookie_name(production), path="/", secure=production, httponly=True, samesite="strict"
    )
