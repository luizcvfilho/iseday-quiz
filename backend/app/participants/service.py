"""All callers own the transaction; locks remain held until commit or rollback."""

import secrets
from collections import defaultdict
from datetime import timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (
    Area,
    Course,
    Participation,
    ParticipationAreaResult,
    ParticipationCourseResult,
    ParticipationSelection,
    QuizVersion,
    School,
    Statement,
    StatementCourseWeight,
)
from app.participants.schemas import (
    AreaResult,
    CourseResult,
    CurrentQuiz,
    ParticipationResult,
    ParticipationSession,
    PublicStatement,
    Registration,
)
from app.participants.security import token_hash
from app.scoring import (
    CourseDefinition,
    CourseWeight,
    InvalidSelectionError,
    ScoringCatalog,
    ScoringConfigurationError,
    StatementDefinition,
    calculate_scores,
)


def require_notice(settings: Settings) -> None:
    if not settings.privacy_notice_version or not settings.privacy_notice_text:
        raise HTTPException(503, "O aviso de uso dos dados ainda não foi configurado.")


def current_quiz(session: Session, settings: Settings) -> CurrentQuiz:
    require_notice(settings)
    version = session.scalar(
        select(QuizVersion).where(QuizVersion.status == "published").with_for_update(read=True)
    )
    if version is None:
        raise HTTPException(503, "Nenhum quiz publicado está disponível.")
    statements = session.scalars(
        select(Statement)
        .where(Statement.quiz_version_id == version.id)
        .order_by(Statement.display_order)
    )
    return CurrentQuiz(
        id=version.id,
        version_number=version.version_number,
        event_name=version.event_name,
        required_selection_count=version.required_selection_count,
        privacy_notice_version=settings.privacy_notice_version,
        privacy_notice_text=settings.privacy_notice_text,
        statements=[
            PublicStatement(id=s.id, display_order=s.display_order, text=s.text) for s in statements
        ],
    )


def find_participation(session: Session, token: str | None) -> Participation | None:
    hashed = token_hash(token)
    if hashed is None:
        return None
    return session.scalar(
        select(Participation)
        .where(Participation.access_token_hash == hashed)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def authenticated_participation(session: Session, token: str | None) -> Participation:
    participant = find_participation(session, token)
    # Check expiry after acquiring the lock, including after a concurrent submit/end.
    now = session.scalar(select(func.clock_timestamp())) if participant else None
    if participant is None or participant.access_expires_at <= now:
        raise HTTPException(401, "Sessão ausente, inválida ou expirada.")
    return participant


def session_summary(participant: Participation) -> ParticipationSession:
    return ParticipationSession(
        id=participant.id,
        quiz_version_id=participant.quiz_version_id,
        status=participant.status,
        access_expires_at=participant.access_expires_at,
    )


def register(
    session: Session, data: Registration, settings: Settings, existing_token: str | None
) -> tuple[ParticipationSession, str, bool]:
    require_notice(settings)
    if data.privacy_notice_version != settings.privacy_notice_version:
        raise HTTPException(409, "O aviso de uso dos dados mudou. Atualize o cadastro.")
    existing = find_participation(session, existing_token)
    if existing and existing.access_expires_at > session.scalar(select(func.clock_timestamp())):
        if any(getattr(existing, key) != value for key, value in data.model_dump().items()):
            raise HTTPException(409, "Encerre a sessão atual antes de iniciar outro cadastro.")
        return session_summary(existing), existing_token, False

    # A share lock synchronizes with archival/publication. A stale version from a
    # previously loaded page cannot accidentally start against the replacement.
    version = session.scalar(
        select(QuizVersion)
        .where(QuizVersion.id == data.quiz_version_id, QuizVersion.status == "published")
        .with_for_update(read=True)
    )
    if version is None:
        raise HTTPException(409, "Essa versão do quiz não está disponível. Atualize a página.")
    school = session.scalar(
        select(School)
        .where(School.id == data.school_id, School.is_active.is_(True))
        .with_for_update(read=True)
    )
    if school is None:
        raise HTTPException(422, "Selecione uma escola ativa da lista.")
    now = session.scalar(select(func.clock_timestamp()))
    token = secrets.token_urlsafe(32)
    participant = Participation(
        **data.model_dump(),
        status="draft",
        started_at=now,
        access_token_hash=token_hash(token),
        access_expires_at=now + timedelta(minutes=settings.participant_session_minutes),
    )
    session.add(participant)
    session.flush()
    return session_summary(participant), token, True


def load_scoring_catalog(session: Session, version_id: UUID) -> ScoringCatalog:
    version = session.get(QuizVersion, version_id)
    if version is None or version.status not in {"published", "archived"}:
        raise ScoringConfigurationError("A participação não tem uma versão publicada.")
    weights = defaultdict(list)
    for link in session.scalars(
        select(StatementCourseWeight).where(StatementCourseWeight.quiz_version_id == version_id)
    ):
        weights[link.statement_id].append(CourseWeight(link.course_id, link.weight))
    return ScoringCatalog(
        quiz_version_id=version_id,
        scoring_method=version.scoring_method,
        area_ids=tuple(session.scalars(select(Area.id).where(Area.quiz_version_id == version_id))),
        courses=tuple(
            CourseDefinition(course.id, course.area_id)
            for course in session.scalars(
                select(Course).where(Course.quiz_version_id == version_id)
            )
        ),
        statements=tuple(
            StatementDefinition(statement_id, tuple(weights[statement_id]))
            for statement_id in session.scalars(
                select(Statement.id).where(Statement.quiz_version_id == version_id)
            )
        ),
    )


def saved_result(session: Session, participant: Participation) -> ParticipationResult:
    if participant.status == "draft":
        raise HTTPException(409, "A participação ainda não foi submetida.")
    area_rows = session.execute(
        select(Area, ParticipationAreaResult)
        .join(ParticipationAreaResult, ParticipationAreaResult.area_id == Area.id)
        .where(ParticipationAreaResult.participation_id == participant.id)
        .order_by(Area.name, Area.id)
    )
    course_rows = session.execute(
        select(Course, ParticipationCourseResult)
        .join(ParticipationCourseResult, ParticipationCourseResult.course_id == Course.id)
        .where(ParticipationCourseResult.participation_id == participant.id)
        .order_by(Course.name, Course.id)
    )
    return ParticipationResult(
        participation_id=participant.id,
        quiz_version_id=participant.quiz_version_id,
        status=participant.status,
        submitted_at=participant.submitted_at,
        statement_ids=list(
            session.scalars(
                select(ParticipationSelection.statement_id)
                .join(Statement, Statement.id == ParticipationSelection.statement_id)
                .where(ParticipationSelection.participation_id == participant.id)
                .order_by(Statement.display_order)
            )
        ),
        areas=[
            AreaResult(id=a.id, name=a.name, score=r.score, is_winner=r.is_winner)
            for a, r in area_rows
        ],
        courses=[
            CourseResult(
                id=c.id,
                area_id=c.area_id,
                name=c.name,
                score=r.score,
                is_recommended=r.is_recommended,
            )
            for c, r in course_rows
        ],
    )


def submit(session: Session, participant: Participation, statement_ids: list[UUID]):
    if participant.status != "draft":
        previous = set(
            session.scalars(
                select(ParticipationSelection.statement_id).where(
                    ParticipationSelection.participation_id == participant.id
                )
            )
        )
        if previous != set(statement_ids):
            raise HTTPException(409, "A participação já foi submetida com outras escolhas.")
        return saved_result(session, participant)
    try:
        score = calculate_scores(
            load_scoring_catalog(session, participant.quiz_version_id), statement_ids
        )
    except InvalidSelectionError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ScoringConfigurationError as exc:
        raise HTTPException(
            503, "O catálogo do quiz está inconsistente. Procure a equipe."
        ) from exc
    common = {"participation_id": participant.id, "quiz_version_id": participant.quiz_version_id}
    session.execute(
        insert(ParticipationSelection),
        [dict(**common, statement_id=statement_id) for statement_id in statement_ids],
    )
    session.execute(
        insert(ParticipationAreaResult),
        [
            dict(**common, area_id=r.area_id, score=r.score, is_winner=r.is_winner)
            for r in score.areas
        ],
    )
    session.execute(
        insert(ParticipationCourseResult),
        [
            dict(**common, course_id=r.course_id, score=r.score, is_recommended=r.is_recommended)
            for r in score.courses
        ],
    )
    participant.status = "submitted"
    participant.submitted_at = session.scalar(select(func.clock_timestamp()))
    session.flush()
    return saved_result(session, participant)
