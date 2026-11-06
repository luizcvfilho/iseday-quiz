from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db import get_session
from app.participants import service
from app.participants.schemas import (
    CurrentQuiz,
    Feedback,
    FeedbackResult,
    ParticipationContacts,
    ParticipationMatch,
    ParticipationResult,
    ParticipationSession,
    QuizContent,
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


def set_session_cookie(
    response: Response, settings: Settings, summary: ParticipationSession, token: str
):
    response.set_cookie(
        cookie_name(settings.app_env == "production"),
        token,
        max_age=max(0, int((summary.access_expires_at - datetime.now(UTC)).total_seconds())),
        expires=summary.access_expires_at.astimezone(UTC),
        path="/",
        secure=settings.app_env == "production",
        httponly=True,
        samesite="strict",
    )


@router.post("/participations/lookup", response_model=ParticipationMatch | None, dependencies=WRITE)
def lookup(data: ParticipationContacts, request: Request, session: Database):
    throttle(
        request, "participation_lookup", request.app.state.settings.participant_registration_limit
    )
    with session.begin():
        return service.lookup_participation(session, data)


@router.post("/participations/resume", response_model=ParticipationSession, dependencies=WRITE)
def resume(data: ParticipationContacts, request: Request, response: Response, session: Database):
    settings = request.app.state.settings
    throttle(request, "participation_resume", settings.participant_registration_limit)
    with session.begin():
        summary, token = service.resume_by_contacts(session, data, settings)
    set_session_cookie(response, settings, summary, token)
    return summary


@router.post("/participations", response_model=ParticipationSession, dependencies=WRITE)
def register(data: Registration, request: Request, response: Response, session: Database):
    settings = request.app.state.settings
    throttle(request, "registration", settings.participant_registration_limit)
    with session.begin():
        summary, token, created = service.register(session, data, settings, access_token(request))
    response.status_code = 201 if created else 200
    set_session_cookie(response, settings, summary, token)
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


@router.get("/participations/me/quiz", response_model=QuizContent)
def participant_quiz(request: Request, session: Database):
    with session.begin():
        return service.participant_quiz(
            session, service.authenticated_participation(session, access_token(request))
        )


@router.get("/participations/me/result", response_model=ParticipationResult)
def result(request: Request, session: Database):
    with session.begin():
        return service.saved_result(
            session, service.authenticated_participation(session, access_token(request))
        )


@router.post("/participations/me/feedback", response_model=FeedbackResult, dependencies=WRITE)
def feedback(data: Feedback, request: Request, session: Database):
    settings = request.app.state.settings
    throttle(request, "feedback", settings.participant_submission_limit)
    hashed = token_hash(access_token(request))
    if hashed:
        request.app.state.public_rate_limiter.check("participant_feedback", hashed, 30)
    with session.begin():
        participant = service.authenticated_participation(session, access_token(request))
        return service.record_feedback(session, participant, data)


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
