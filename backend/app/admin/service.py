from collections import defaultdict
from datetime import datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin.schemas import (
    CatalogItem,
    CountItem,
    Filters,
    NamedItem,
    Options,
    ParticipationDetail,
    ParticipationPage,
    ParticipationRow,
    Summary,
    VersionItem,
)
from app.models import (
    Area,
    Course,
    Participation,
    ParticipationAreaResult,
    ParticipationCourseResult,
    ParticipationFeedback,
    ParticipationSelection,
    QuizVersion,
    School,
    Statement,
)
from app.participants.schemas import PublicStatement
from app.participants.service import saved_result

EVENT_ZONE = ZoneInfo("America/Sao_Paulo")


def filtered_ids(filters: Filters):
    query = select(Participation.id)
    if filters.q.strip():
        query = query.where(Participation.full_name.icontains(filters.q.strip(), autoescape=True))
    for field in ("school_id", "quiz_version_id", "status"):
        value = getattr(filters, field)
        if value is not None:
            query = query.where(getattr(Participation, field) == value)
    if filters.date_from:
        query = query.where(
            Participation.started_at >= datetime.combine(filters.date_from, time.min, EVENT_ZONE)
        )
    if filters.date_to:
        query = query.where(
            Participation.started_at
            < datetime.combine(filters.date_to + timedelta(days=1), time.min, EVENT_ZONE)
        )
    for model, field, value, flag in (
        (ParticipationAreaResult, "area_id", filters.area_id, "is_winner"),
        (ParticipationCourseResult, "course_id", filters.course_id, "is_recommended"),
    ):
        if value is not None:
            query = query.where(
                select(model.participation_id)
                .where(
                    model.participation_id == Participation.id,
                    getattr(model, field) == value,
                    getattr(model, flag).is_(True),
                )
                .exists()
            )
    if filters.agreement is not None:
        feedback = select(ParticipationFeedback.participation_id).where(
            ParticipationFeedback.participation_id == Participation.id
        )
        if filters.agreement == "pending":
            query = query.where(~feedback.exists())
        else:
            query = query.where(
                feedback.where(
                    ParticipationFeedback.agrees_with_result.is_(filters.agreement == "yes")
                ).exists()
            )
    return query


def options(session: Session) -> Options:
    return Options(
        schools=[
            NamedItem(id=s.id, name=s.name)
            for s in session.scalars(select(School).order_by(School.name))
        ],
        versions=[
            VersionItem(id=v.id, name=v.event_name, version_number=v.version_number)
            for v in session.scalars(
                select(QuizVersion).order_by(QuizVersion.version_number.desc())
            )
        ],
        **{
            key: [
                CatalogItem(id=row.id, name=row.name, quiz_version_id=row.quiz_version_id)
                for row in session.scalars(select(model).order_by(model.name, model.id))
            ]
            for key, model in (("areas", Area), ("courses", Course))
        },
    )


def rows(session: Session, query) -> list[ParticipationRow]:
    records = session.execute(
        select(Participation, School, QuizVersion, ParticipationFeedback.agrees_with_result)
        .join(School, School.id == Participation.school_id)
        .join(QuizVersion, QuizVersion.id == Participation.quiz_version_id)
        .outerjoin(
            ParticipationFeedback, ParticipationFeedback.participation_id == Participation.id
        )
        .where(Participation.id.in_(query))
        .order_by(Participation.started_at.desc(), Participation.id.desc())
    ).all()
    ids = [p.id for p, *_ in records]
    areas, courses = defaultdict(list), defaultdict(list)
    if ids:
        for model, item, flag, key, target in (
            (ParticipationAreaResult, Area, "is_winner", "area_id", areas),
            (ParticipationCourseResult, Course, "is_recommended", "course_id", courses),
        ):
            for pid, entity in session.execute(
                select(model.participation_id, item)
                .join(item, item.id == getattr(model, key))
                .where(model.participation_id.in_(ids), getattr(model, flag).is_(True))
                .order_by(item.name, item.id)
            ):
                target[pid].append(NamedItem(id=entity.id, name=entity.name))
    return [
        ParticipationRow(
            id=p.id,
            full_name=p.full_name,
            school=NamedItem(id=school.id, name=school.name),
            quiz_version_id=p.quiz_version_id,
            version_number=version.version_number,
            status=p.status,
            started_at=p.started_at,
            submitted_at=p.submitted_at,
            completed_at=p.completed_at,
            agrees_with_result=agreement,
            winning_areas=areas[p.id],
            recommended_courses=courses[p.id],
        )
        for p, school, version, agreement in records
    ]


def participations(session: Session, filters: Filters, page: int, page_size: int):
    query = filtered_ids(filters)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    ids = (
        query.order_by(Participation.started_at.desc(), Participation.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return ParticipationPage(items=rows(session, ids), total=total, page=page, page_size=page_size)


def detail(session: Session, participation_id: UUID):
    participant = session.get(Participation, participation_id)
    if participant is None:
        raise HTTPException(404, "Participação não encontrada.")
    row = rows(session, select(Participation.id).where(Participation.id == participation_id))[0]
    version = session.get(QuizVersion, participant.quiz_version_id)
    selections = session.scalars(
        select(Statement)
        .join(ParticipationSelection, ParticipationSelection.statement_id == Statement.id)
        .where(ParticipationSelection.participation_id == participation_id)
        .order_by(Statement.display_order, Statement.id)
    )
    return ParticipationDetail(
        **row.model_dump(),
        email=participant.email,
        phone=participant.phone,
        event_name=version.event_name,
        privacy_notice_version=participant.privacy_notice_version,
        selections=[
            PublicStatement(id=s.id, display_order=s.display_order, text=s.text) for s in selections
        ],
        result=saved_result(session, participant) if participant.status != "draft" else None,
    )


def summary(session: Session, filters: Filters):
    ids = filtered_ids(filters).subquery()
    counts = dict(
        session.execute(
            select(Participation.status, func.count())
            .where(Participation.id.in_(select(ids.c.id)))
            .group_by(Participation.status)
        ).all()
    )
    feedback = dict(
        session.execute(
            select(ParticipationFeedback.agrees_with_result, func.count())
            .where(ParticipationFeedback.participation_id.in_(select(ids.c.id)))
            .group_by(ParticipationFeedback.agrees_with_result)
        ).all()
    )
    agreed, disagreed = feedback.get(True, 0), feedback.get(False, 0)
    schools = session.execute(
        select(School.id, School.name, func.count().label("count"))
        .join(Participation, Participation.school_id == School.id)
        .where(Participation.id.in_(select(ids.c.id)))
        .group_by(School.id)
        .order_by(func.count().desc(), School.name, School.id)
    )
    groups = {}
    for name, model, entity, key, flag in (
        ("areas", ParticipationAreaResult, Area, "area_id", "is_winner"),
        ("courses", ParticipationCourseResult, Course, "course_id", "is_recommended"),
    ):
        groups[name] = [
            CountItem(id=id, name=label, count=count, version_number=version)
            for id, label, version, count in session.execute(
                select(
                    entity.id, entity.name, QuizVersion.version_number, func.count().label("count")
                )
                .select_from(entity)
                .join(model, getattr(model, key) == entity.id)
                .join(QuizVersion, QuizVersion.id == entity.quiz_version_id)
                .where(model.participation_id.in_(select(ids.c.id)), getattr(model, flag).is_(True))
                .group_by(entity.id, QuizVersion.version_number)
                .order_by(func.count().desc(), entity.name, entity.id)
            )
        ]
    return Summary(
        total=sum(counts.values()),
        draft=counts.get("draft", 0),
        submitted=counts.get("submitted", 0),
        completed=counts.get("completed", 0),
        agreed=agreed,
        disagreed=disagreed,
        agreement_rate=round(100 * agreed / (agreed + disagreed), 1)
        if agreed + disagreed
        else None,
        schools=[CountItem(id=id, name=name, count=count) for id, name, count in schools],
        **groups,
    )
