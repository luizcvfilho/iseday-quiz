"""Administrative exports of registration data, saved results and confirmation."""

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
from app.models import Participation

HEADERS = (
    "Nome",
    "Escola",
    "Telefone",
    "E-mail",
    "Áreas vencedoras",
    "Cursos sugeridos",
    "Confirmação",
)


def export_rows(session: Session, filters: Filters):
    query = service.filtered_ids(filters)
    count = session.scalar(select(func.count()).select_from(query.subquery()))
    if count > 10000:
        raise HTTPException(
            422, "A exportação permite até 10.000 participações. Restrinja os filtros."
        )
    contacts = {
        row.id: (row.phone, row.email)
        for row in session.execute(
            select(
                Participation.id,
                Participation.phone,
                Participation.email,
            ).where(Participation.id.in_(query))
        )
    }
    return [
        (
            row.full_name,
            row.school_name,
            *contacts[row.id],
            ", ".join(area.name for area in row.winning_areas),
            ", ".join(course.name for course in row.recommended_courses),
            "Sem resposta"
            if row.agrees_with_result is None
            else "Concordou"
            if row.agrees_with_result
            else "Discordou",
        )
        for row in service.rows(session, query)
    ]


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
    for column, width in zip("ABCDEFG", (35, 35, 22, 40, 50, 85, 20), strict=True):
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
    sheet.auto_filter.ref = f"A1:G{row_number}"
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
