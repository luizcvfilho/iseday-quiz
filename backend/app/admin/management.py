"""Administrative preparation. The caller owns the transaction and audit log."""

import csv
import hashlib
from io import StringIO
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.orm import Session

from app.admin import management_schemas as schema
from app.admin import service
from app.admin.schemas import Filters
from app.catalog import (
    DEFAULT_WORKBOOK,
    PSYCHOLOGY_DESTINATION,
    PSYCHOLOGY_INSTRUCTIONS,
    REVIEW_NOTES,
    _catalog_rows,
    read_catalog,
)
from app.models import (
    Area,
    Course,
    QuizVersion,
    Statement,
    StatementCourseWeight,
)
from app.participants.service import load_scoring_catalog
from app.scoring import ScoringConfigurationError, calculate_scores

LEGACY_COURSE_GROUPS = {
    "Enfermagem": "Enfermagem e Fisioterapia",
    "Fisioterapia": "Enfermagem e Fisioterapia",
    "Engenharia Civil": "Engenharia Civil e Mecânica",
    "Engenharia Mecânica": "Engenharia Civil e Mecânica",
}


def version(session: Session, version_id: UUID, *, draft=False):
    item = session.get(QuizVersion, version_id, with_for_update=draft)
    if item is None:
        raise HTTPException(404, "Versão não encontrada.")
    if draft and item.status != "draft":
        raise HTTPException(
            409, "Somente rascunhos podem ser editados. Crie uma cópia desta versão."
        )
    return item


def version_item(session: Session, item: QuizVersion):
    return schema.VersionItem(
        id=item.id,
        event_name=item.event_name,
        version_number=item.version_number,
        status=item.status,
        created_at=item.created_at,
        statement_count=session.scalar(
            select(func.count()).select_from(Statement).where(Statement.quiz_version_id == item.id)
        ),
    )


def versions(session: Session):
    return [
        version_item(session, item)
        for item in session.scalars(select(QuizVersion).order_by(QuizVersion.version_number.desc()))
    ]


def version_detail(session: Session, version_id: UUID):
    item = version(session, version_id)
    areas = session.scalars(select(Area).where(Area.quiz_version_id == item.id).order_by(Area.name))
    courses = session.scalars(
        select(Course).where(Course.quiz_version_id == item.id).order_by(Course.name)
    )
    statements = session.scalars(
        select(Statement)
        .where(Statement.quiz_version_id == item.id)
        .order_by(Statement.display_order)
    )
    course_names = dict(
        session.execute(
            select(Course.id, Course.name).where(Course.quiz_version_id == item.id)
        ).all()
    )
    links = {}
    for link in session.scalars(
        select(StatementCourseWeight).where(StatementCourseWeight.quiz_version_id == item.id)
    ):
        links.setdefault(link.statement_id, []).append(
            {
                "course_id": link.course_id,
                "course": course_names[link.course_id],
                "weight": link.weight,
            }
        )
    result = schema.VersionDetail(
        **version_item(session, item).model_dump(),
        revision="",
        psychology_destination=item.psychology_destination,
        psychology_instructions=item.psychology_instructions,
        areas=[
            schema.AreaItem(
                id=a.id,
                name=a.name,
                destination=a.destination,
                destination_instructions=a.destination_instructions,
            )
            for a in areas
        ],
        courses=[
            schema.CourseItem(
                id=c.id,
                name=c.name,
                area_id=c.area_id,
                destination=c.destination,
                destination_instructions=c.destination_instructions,
            )
            for c in courses
        ],
        review_notes=list(REVIEW_NOTES),
        statements=[
            {
                "id": s.id,
                "number": s.source_number,
                "text": s.text,
                "courses": sorted(links.get(s.id, []), key=lambda link: link["course"]),
            }
            for s in statements
        ],
    )
    result.revision = hashlib.sha256(
        result.model_dump_json(exclude={"revision"}).encode()
    ).hexdigest()
    return result


def create_version(session: Session, data: schema.NewVersion):
    # Shared with the CLI importer: allocate numbers and publish under the same lock.
    session.execute(text("SELECT pg_advisory_xact_lock(735020251)"))
    source = version(session, data.source_version_id) if data.source_version_id else None
    if source:
        # Include the version's own fields in the same locked snapshot as its children.
        session.refresh(source, with_for_update=True)
    item = QuizVersion(
        id=uuid4(),
        event_name=data.event_name,
        version_number=(session.scalar(select(func.max(QuizVersion.version_number))) or 0) + 1,
        psychology_destination=source.psychology_destination if source else PSYCHOLOGY_DESTINATION,
        psychology_instructions=source.psychology_instructions
        if source
        else PSYCHOLOGY_INSTRUCTIONS,
    )
    session.add(item)
    session.flush()
    if source is None:
        for model, records in _catalog_rows(read_catalog(DEFAULT_WORKBOOK), item.id):
            session.execute(insert(model), records)
    else:
        mappings = {}
        for model in (Area, Course, Statement, StatementCourseWeight):
            for original in session.scalars(
                select(model).where(model.quiz_version_id == source.id)
            ):
                values = {
                    column.name: getattr(original, column.name)
                    for column in model.__table__.columns
                }
                values["quiz_version_id"] = item.id
                if "id" in values:
                    mappings[values["id"]] = values["id"] = uuid4()
                for key in ("area_id", "course_id", "statement_id"):
                    if key in values:
                        values[key] = mappings[values[key]]
                session.execute(insert(model).values(**values))
        _group_courses(session, item.id)
    session.flush()
    return version_detail(session, item.id)


def _group_courses(session: Session, version_id: UUID):
    """Consolidate legacy courses only in the newly copied draft."""
    groups = {}
    for course in session.scalars(
        select(Course).where(Course.quiz_version_id == version_id).order_by(Course.name)
    ):
        name = LEGACY_COURSE_GROUPS.get(course.name, course.name)
        groups.setdefault(name, []).append(course)
    for name, courses in groups.items():
        if len(courses) == 1 and courses[0].name == name:
            continue
        if len({(c.area_id, c.destination, c.destination_instructions) for c in courses}) != 1:
            raise HTTPException(
                422,
                f"Não foi possível agrupar {name}: áreas ou destinos divergentes. "
                "Ajuste os destinos em um rascunho antes de copiá-lo.",
            )
        target = next((c for c in courses if c.name == name), courses[0])
        course_ids = [c.id for c in courses]
        weights = {}
        for link in session.scalars(
            select(StatementCourseWeight).where(StatementCourseWeight.course_id.in_(course_ids))
        ):
            # A shared statement contributes once; retain the strongest existing weight.
            weights[link.statement_id] = max(weights.get(link.statement_id, 0), link.weight)
        session.execute(
            delete(StatementCourseWeight).where(StatementCourseWeight.course_id.in_(course_ids))
        )
        session.execute(
            delete(Course).where(Course.id.in_([c.id for c in courses if c.id != target.id]))
        )
        target.name = name
        target.description = (
            "\n\n".join(dict.fromkeys(c.description for c in courses if c.description)) or None
        )
        if weights:
            session.execute(
                insert(StatementCourseWeight),
                [
                    dict(
                        quiz_version_id=version_id,
                        statement_id=statement_id,
                        course_id=target.id,
                        weight=weight,
                    )
                    for statement_id, weight in weights.items()
                ],
            )


def save_version(session: Session, version_id: UUID, data: schema.VersionInput):
    item = version(session, version_id, draft=True)
    if version_detail(session, item.id).revision != data.expected_revision:
        raise HTTPException(409, "Este rascunho foi alterado. Recarregue a versão antes de salvar.")
    for model, entries, fields in (
        (Area, data.areas, ("destination", "destination_instructions")),
        (Course, data.courses, ("destination", "destination_instructions")),
    ):
        records = {
            r.id: r for r in session.scalars(select(model).where(model.quiz_version_id == item.id))
        }
        if len(entries) != len(records) or {e.id for e in entries} != set(records):
            raise HTTPException(
                422, "Áreas e cursos devem pertencer à versão e aparecer uma única vez."
            )
        for entry in entries:
            for field in fields:
                setattr(records[entry.id], field, getattr(entry, field))
    for field in ("event_name", "psychology_destination", "psychology_instructions"):
        setattr(item, field, getattr(data, field))
    save_statements(session, item.id, data.statements)
    session.flush()
    return version_detail(session, item.id)


def save_statements(session: Session, version_id: UUID, entries: list[schema.StatementInput]):
    records = {
        s.id: s
        for s in session.scalars(select(Statement).where(Statement.quiz_version_id == version_id))
    }
    existing_ids = {entry.id for entry in entries if entry.id is not None}
    if existing_ids != set(records):
        raise HTTPException(
            422, "Inclua todas as afirmativas existentes, sem usar IDs de outra versão."
        )
    course_ids = set(session.scalars(select(Course.id).where(Course.quiz_version_id == version_id)))
    if any(link.course_id not in course_ids for entry in entries for link in entry.courses):
        raise HTTPException(422, "Os cursos dos pesos devem pertencer à versão editada.")
    next_number = max((s.source_number for s in records.values()), default=0)
    next_order = max((s.display_order for s in records.values()), default=0)
    new_count = sum(entry.id is None for entry in entries)
    if max(next_number, next_order) + new_count > 32767:
        raise HTTPException(422, "O limite de numeração das afirmativas foi atingido.")
    weights = []
    for entry in entries:
        if entry.id is None:
            next_number += 1
            next_order += 1
            statement = Statement(
                id=uuid4(),
                quiz_version_id=version_id,
                source_number=next_number,
                display_order=next_order,
                text=entry.text,
            )
            session.add(statement)
        else:
            statement = records[entry.id]
            statement.text = entry.text
        weights.extend(
            {
                "quiz_version_id": version_id,
                "statement_id": statement.id,
                "course_id": link.course_id,
                "weight": link.weight,
            }
            for link in entry.courses
        )
    session.flush()
    session.execute(
        delete(StatementCourseWeight).where(StatementCourseWeight.quiz_version_id == version_id)
    )
    if weights:
        session.execute(insert(StatementCourseWeight), weights)


def publish(session: Session, version_id: UUID, data: schema.PublishVersion):
    session.execute(text("SELECT pg_advisory_xact_lock(735020251)"))
    item = version(session, version_id, draft=True)
    if version_detail(session, item.id).revision != data.expected_revision:
        raise HTTPException(
            409, "O conteúdo mudou. Recarregue e revise a versão antes de publicar."
        )
    current = session.scalar(
        select(QuizVersion).where(QuizVersion.status == "published").with_for_update()
    )
    if (current.id if current else None) != data.expected_published_id:
        raise HTTPException(
            409, "A versão publicada mudou. Atualize a lista e revise a publicação."
        )
    catalog = load_scoring_catalog(session, item.id, allow_draft=True)
    if len(catalog.statements) < 25:
        raise HTTPException(422, "A publicação exige pelo menos 25 afirmativas.")
    try:
        calculate_scores(catalog, [s.id for s in catalog.statements[:25]])
    except ScoringConfigurationError as exc:
        raise HTTPException(422, "Catálogo inconsistente. Revise os vínculos e pesos.") from exc
    linked = {w.course_id for s in catalog.statements for w in s.weights}
    if linked != {c.id for c in catalog.courses} or {c.area_id for c in catalog.courses} != set(
        catalog.area_ids
    ):
        raise HTTPException(
            422, "Todas as áreas e cursos precisam estar vinculados às afirmativas."
        )
    if current:
        current.status = "archived"
        session.flush()
    item.status = "published"
    session.flush()
    return version_detail(session, item.id)


def archive(session: Session, version_id: UUID):
    session.execute(text("SELECT pg_advisory_xact_lock(735020251)"))
    item = session.get(QuizVersion, version_id, with_for_update=True)
    if item is None:
        raise HTTPException(404, "Versão não encontrada.")
    if item.status != "published":
        raise HTTPException(409, "Somente a versão publicada pode ser arquivada.")
    item.status = "archived"
    session.flush()
    return version_detail(session, item.id)


def export_csv(session: Session, filters: Filters):
    query = service.filtered_ids(filters)
    count = session.scalar(select(func.count()).select_from(query.subquery()))
    if count > 10000:
        raise HTTPException(
            422, "A exportação permite até 10.000 participações. Restrinja os filtros."
        )
    output = StringIO(newline="")
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(
        [
            "Participação",
            "Nome",
            "Escola",
            "Versão",
            "Situação",
            "Início (Brasília)",
            "Áreas vencedoras",
            "Cursos sugeridos",
            "Confirmação",
        ]
    )
    labels = {"draft": "Em andamento", "submitted": "Aguarda confirmação", "completed": "Concluída"}
    for row in service.rows(session, query):
        cells = [
            str(row.id),
            row.full_name,
            row.school_name,
            row.version_number,
            labels[row.status],
            row.started_at.astimezone(service.EVENT_ZONE).strftime("%d/%m/%Y %H:%M:%S"),
            " | ".join(a.name for a in row.winning_areas),
            " | ".join(c.name for c in row.recommended_courses),
            "Sem resposta"
            if row.agrees_with_result is None
            else "Concordou"
            if row.agrees_with_result
            else "Discordou",
        ]
        # Quoting alone does not prevent spreadsheet formula execution.
        writer.writerow(
            [
                "'" + c
                if isinstance(c, str)
                and c.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n"))
                else c
                for c in cells
            ]
        )
    return output.getvalue()
