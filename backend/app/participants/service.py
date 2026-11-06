"""All callers own the transaction; locks remain held until commit or rollback."""

import secrets
from collections import defaultdict
from datetime import timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.catalog import EVENT_NAME, PSYCHOLOGY_DESTINATION, PSYCHOLOGY_INSTRUCTIONS
from app.core.config import Settings
from app.models import (
    Area,
    Course,
    Participation,
    ParticipationAreaResult,
    ParticipationCourseResult,
    ParticipationFeedback,
    ParticipationSelection,
    Statement,
    StatementCourseWeight,
)
from app.participants.schemas import (
    AreaResult,
    CourseResult,
    CurrentQuiz,
    Feedback,
    FeedbackResult,
    ParticipationResult,
    ParticipationSession,
    PublicStatement,
    QuizContent,
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
    return CurrentQuiz(
        **quiz_content(session).model_dump(),
        privacy_notice_version=settings.privacy_notice_version,
        privacy_notice_text=settings.privacy_notice_text,
    )


def quiz_content(session: Session) -> QuizContent:
    statements = list(session.scalars(select(Statement).order_by(Statement.display_order)))
    if len(statements) < 25:
        raise HTTPException(
            503, "O catálogo fixo do quiz não está disponível. Execute as migrações."
        )
    return QuizContent(
        event_name=EVENT_NAME,
        required_selection_count=25,
        statements=[
            PublicStatement(id=s.id, display_order=s.display_order, text=s.text) for s in statements
        ],
    )


def participant_quiz(session: Session, participant: Participation) -> QuizContent:
    return quiz_content(session)


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
            raise HTTPException(
                409, "Já existe uma participação em andamento. Atualize a página para retomá-la."
            )
        return session_summary(existing), existing_token, False

    quiz_content(session)
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


def load_scoring_catalog(session: Session) -> ScoringCatalog:
    weights = defaultdict(list)
    for link in session.scalars(select(StatementCourseWeight)):
        weights[link.statement_id].append(CourseWeight(link.course_id, link.weight))
    return ScoringCatalog(
        area_ids=tuple(session.scalars(select(Area.id))),
        courses=tuple(
            CourseDefinition(course.id, course.area_id)
            for course in session.scalars(select(Course))
        ),
        statements=tuple(
            StatementDefinition(statement_id, tuple(weights[statement_id]))
            for statement_id in session.scalars(select(Statement.id))
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
            AreaResult(
                id=a.id,
                name=a.name,
                destination=a.destination,
                score=r.score,
                is_winner=r.is_winner,
            )
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
        feedback=(
            saved_feedback(session, participant) if participant.status == "completed" else None
        ),
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
        score = calculate_scores(load_scoring_catalog(session), statement_ids)
    except InvalidSelectionError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ScoringConfigurationError as exc:
        raise HTTPException(
            503, "O catálogo do quiz está inconsistente. Procure a equipe."
        ) from exc
    common = {"participation_id": participant.id}
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


def saved_feedback(session: Session, participant: Participation) -> FeedbackResult:
    feedback = session.get(ParticipationFeedback, participant.id)
    if participant.status != "completed" or feedback is None:
        raise HTTPException(503, "Não foi possível recuperar a confirmação. Procure a equipe.")
    return FeedbackResult(
        participation_id=participant.id,
        status=participant.status,
        completed_at=participant.completed_at,
        agrees_with_result=feedback.agrees_with_result,
        chosen_course_id=feedback.chosen_course_id,
        destination=feedback.destination,
        destination_instructions=feedback.destination_instructions,
        answered_at=feedback.answered_at,
    )


def record_feedback(session: Session, participant: Participation, data: Feedback) -> FeedbackResult:
    """Save the latest answer and destination under the participant's existing lock."""
    if participant.status == "draft":
        raise HTTPException(409, "Submeta as escolhas antes de confirmar o resultado.")
    if participant.status == "completed":
        previous = saved_feedback(session, participant)
        if (
            previous.agrees_with_result == data.agrees_with_result
            and previous.chosen_course_id == data.chosen_course_id
        ):
            return previous

    if data.agrees_with_result:
        query = (
            select(Course)
            .join(ParticipationCourseResult, ParticipationCourseResult.course_id == Course.id)
            .where(
                ParticipationCourseResult.participation_id == participant.id,
                ParticipationCourseResult.is_recommended.is_(True),
            )
            .order_by(Course.name, Course.id)
        )
        # Accept an explicit course from older clients; the current flow uses every
        # saved recommendation, preserving ties without asking the student to choose.
        if data.chosen_course_id is not None:
            query = query.where(Course.id == data.chosen_course_id)
        courses = list(session.scalars(query))
        if not courses:
            raise HTTPException(422, "Não foi possível encontrar os cursos sugeridos.")
        if len(courses) == 1:
            destination = f"Estande de {courses[0].name} — Ginásio"
            instructions = (
                f"Vá ao ginásio e visite o estande de {courses[0].name} "
                "para conhecer o curso e conversar com a equipe."
            )
        else:
            destination = "Estandes dos cursos indicados — Ginásio"
            instructions = "Vá ao ginásio e visite os estandes dos cursos indicados pelo quiz:\n"
            instructions += "\n".join(f"• {course.name}" for course in courses)
    else:
        destination, instructions = PSYCHOLOGY_DESTINATION, PSYCHOLOGY_INSTRUCTIONS

    now = session.scalar(select(func.clock_timestamp()))
    if participant.status == "completed":
        feedback = session.get(ParticipationFeedback, participant.id)
        feedback.agrees_with_result = data.agrees_with_result
        feedback.chosen_course_id = data.chosen_course_id
        feedback.destination = destination
        feedback.destination_instructions = instructions
        feedback.answered_at = now
    else:
        session.add(
            ParticipationFeedback(
                participation_id=participant.id,
                agrees_with_result=data.agrees_with_result,
                chosen_course_id=data.chosen_course_id,
                destination=destination,
                destination_instructions=instructions,
                answered_at=now,
            )
        )
        # Insert before completing; later revisions preserve the initial completion time.
        session.flush()
        participant.status = "completed"
        participant.completed_at = now
    session.flush()
    return saved_feedback(session, participant)
