"""Administrative CSV export of participation results."""

import csv
from io import StringIO

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin import service
from app.admin.schemas import Filters


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
