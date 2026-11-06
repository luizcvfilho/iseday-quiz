"""Administrative exports of registration data and saved final referrals."""

import csv
from io import BytesIO, StringIO

from fastapi import HTTPException
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin import service
from app.admin.schemas import Filters
from app.models import Participation, ParticipationFeedback

HEADERS = (
    "Nome",
    "Escola",
    "Telefone",
    "E-mail",
    "Encaminhamento final",
    "Orientações do encaminhamento",
)


def export_rows(session: Session, filters: Filters):
    query = service.filtered_ids(filters)
    count = session.scalar(select(func.count()).select_from(query.subquery()))
    if count > 10000:
        raise HTTPException(
            422, "A exportação permite até 10.000 participações. Restrinja os filtros."
        )
    return session.execute(
        select(
            Participation.full_name,
            Participation.school_name,
            Participation.phone,
            Participation.email,
            ParticipationFeedback.destination,
            ParticipationFeedback.destination_instructions,
        )
        .outerjoin(
            ParticipationFeedback, ParticipationFeedback.participation_id == Participation.id
        )
        .where(Participation.id.in_(query))
        .order_by(Participation.started_at.desc(), Participation.id.desc())
    )


def export_csv(session: Session, filters: Filters):
    rows = export_rows(session, filters)
    output = StringIO(newline="")
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(HEADERS)
    for row in rows:
        # Quoting alone does not prevent spreadsheet formula execution.
        writer.writerow(
            [
                "'" + c
                if isinstance(c, str)
                and c.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n"))
                else c
                for c in row
            ]
        )
    return output.getvalue()


def export_xlsx(session: Session, filters: Filters):
    rows = export_rows(session, filters)
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Participações")
    sheet.freeze_panes = "A2"
    for column, width in zip("ABCDEF", (35, 35, 22, 40, 50, 85), strict=True):
        sheet.column_dimensions[column].width = width
    headers = [WriteOnlyCell(sheet, value=header) for header in HEADERS]
    for cell in headers:
        cell.font = Font(bold=True)
    sheet.append(headers)
    row_number = 1
    for row in rows:
        row_number += 1
        cells = []
        for value in row:
            cell = WriteOnlyCell(sheet, value=value or "")
            # Explicit strings preserve phone numbers and prevent formula execution.
            cell.data_type = "s"
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cells.append(cell)
        sheet.append(cells)
    sheet.auto_filter.ref = f"A1:F{row_number}"
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
