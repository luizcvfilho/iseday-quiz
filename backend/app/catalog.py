"""Validate the ISE Day workbook and import an immutable snapshot as a draft.

Run ``python -m app.catalog --help`` from backend/. No publication is performed.
"""

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4, uuid5
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from pydantic import ValidationError
from sqlalchemy import insert, select, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db import build_engine
from app.models import Area, Course, QuizVersion, Statement, StatementCourseWeight

DEFAULT_WORKBOOK = Path(__file__).resolve().parents[1] / "catalog" / "quiz-final.xlsx"
SCORING_METHOD = "area_distinct_count_course_sum_v1"
PSYCHOLOGY_DESTINATION = "SPA"
PSYCHOLOGY_INSTRUCTIONS = "Procure a equipe de Psicologia no SPA."
PENDING_INSTRUCTIONS = (
    "Referência da planilha por área; confirmar localização e encaminhamento com a instituição."
)
# Expand only known labels. Splitting on 'e' would corrupt Arquitetura e Urbanismo.
COURSE_LABELS = {
    "Enfermagem e Fisioterapia": ("Enfermagem", "Fisioterapia"),
    "Engenharia Civil e Mecânica": ("Engenharia Civil", "Engenharia Mecânica"),
    "Arquitetura": ("Arquitetura e Urbanismo",),
}
EXPECTED_COURSES = {
    "Enfermagem": "Saúde",
    "Fisioterapia": "Saúde",
    "Educação Física": "Saúde",
    "Psicologia": "Saúde",
    "Engenharia Civil": "Engenharia",
    "Engenharia Mecânica": "Engenharia",
    "Engenharia de Produção": "Engenharia",
    "Administração": "Negócios",
    "Direito": "Negócios",
    "Pedagogia": "Educação",
    "Arquitetura e Urbanismo": "Arquitetura",
}
REVIEW_NOTES = (
    "Rascunho: catálogo, textos, metodologia, pesos e destinos aguardam validação institucional.",
    "A planilha contém 74 afirmativas; o PDF menciona 82. As fontes não foram mescladas.",
    "Textos preservados: revisar especialmente 29 (Colcar) e 34 (instuição).",
    "Peso proposto: 1 por vínculo; área conta uma vez por frase; sem normalização automática.",
    "Cobertura desigual entre áreas; a soma bruta pode favorecer áreas com mais afirmativas.",
    "Destinos são listas por área; confirmar correspondência por curso e localização.",
    "Confirmar a divergência da localização do Escritório Modelo entre planilha e PDF.",
)


class CatalogError(ValueError):
    """Invalid content or a conflicting existing version."""


@dataclass(frozen=True)
class AreaData:
    name: str
    destination: str


@dataclass(frozen=True)
class CourseData:
    name: str
    area: str


@dataclass(frozen=True)
class StatementData:
    source_number: int
    display_order: int
    text: str
    courses: tuple[str, ...]


@dataclass(frozen=True)
class Catalog:
    source_sha256: str
    areas: tuple[AreaData, ...]
    courses: tuple[CourseData, ...]
    statements: tuple[StatementData, ...]

    def report(self) -> dict:
        course_areas = {course.name: course.area for course in self.courses}
        coverage = Counter(
            area
            for statement in self.statements
            for area in {course_areas[course] for course in statement.courses}
        )
        signatures = {
            course.name: tuple(s.source_number for s in self.statements if course.name in s.courses)
            for course in self.courses
        }
        groups: dict[tuple[int, ...], list[str]] = {}
        for course, signature in signatures.items():
            groups.setdefault(signature, []).append(course)
        return {
            "source_file": "QUIZ FINAL.xlsx",
            **asdict(self),
            "status": "draft",
            "scoring_method": SCORING_METHOD,
            "weight_per_link": 1,
            "required_selection_count": 25,
            "psychology_destination": PSYCHOLOGY_DESTINATION,
            "psychology_instructions": PSYCHOLOGY_INSTRUCTIONS,
            "area_destination_instructions": PENDING_INSTRUCTIONS,
            "counts": {
                "statements": len(self.statements),
                "courses": len(self.courses),
                "areas": len(self.areas),
                "links": sum(len(s.courses) for s in self.statements),
            },
            "area_coverage": dict(sorted(coverage.items())),
            "course_coverage": {name: len(ids) for name, ids in signatures.items()},
            "identical_course_mappings": [names for names in groups.values() if len(names) > 1],
            "review_notes": REVIEW_NOTES,
        }


def _string(value, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogError(f"{location}: texto obrigatório.")
    if value != value.strip():
        raise CatalogError(f"{location}: revise os espaços no início/fim do texto.")
    return value


def _rows(workbook, sheet_name: str, columns: int):
    if sheet_name not in workbook.sheetnames:
        raise CatalogError(f"Aba obrigatória ausente: {sheet_name}.")
    for row in workbook[sheet_name].iter_rows():
        if not any(cell.value is not None for cell in row):
            continue
        location = f"{sheet_name}!linha {row[0].row}"
        if any(cell.data_type in {"f", "e"} for cell in row):
            raise CatalogError(f"{location}: fórmulas e erros de célula não são aceitos.")
        if any(cell.value is not None for cell in row[columns:]):
            raise CatalogError(f"{location}: coluna inesperada com conteúdo.")
        values = [cell.value for cell in row[:columns]]
        yield location, values + [None] * (columns - len(values))


def _header(rows, expected: tuple, sheet_name: str):
    first = next(rows, None)
    if first is None or tuple(first[1]) != expected:
        raise CatalogError(f"{sheet_name}: cabeçalho diferente do modelo esperado.")


def read_catalog(path: Path) -> Catalog:
    # Hash and parse the same bytes, so the report identifies the exact imported source.
    content = path.read_bytes()
    workbook = load_workbook(BytesIO(content), data_only=False)
    try:
        return _parse_workbook(workbook, hashlib.sha256(content).hexdigest())
    finally:
        workbook.close()


def _parse_workbook(workbook, source_sha256: str) -> Catalog:
    rows = iter(_rows(workbook, "Tabela_Area", 3))
    _header(rows, ("Cursos", "Área", "Espaços de vivência prática no campus"), "Tabela_Area")
    courses: dict[str, CourseData] = {}
    areas: dict[str, AreaData] = {}
    for location, (name, area, destination) in rows:
        name, area, destination = (_string(value, location) for value in (name, area, destination))
        if name in courses:
            raise CatalogError(f"{location}: curso duplicado: {name}.")
        if EXPECTED_COURSES.get(name) != area:
            raise CatalogError(f"{location}: curso/área desconhecido ou divergente: {name}/{area}.")
        if area in areas and areas[area].destination != destination:
            raise CatalogError(f"{location}: destinos divergentes para a área {area}.")
        courses[name] = CourseData(name, area)
        areas[area] = AreaData(area, destination)
    if set(courses) != set(EXPECTED_COURSES):
        raise CatalogError("Tabela_Area: são obrigatórios os 11 cursos e as 5 áreas do catálogo.")

    rows = iter(_rows(workbook, "Tabela_Cursos", 4))
    _header(
        rows,
        ("Marque as frase que mais se identifica", None, "Curso Sugerido 1", "Curso Sugerido 2"),
        "Tabela_Cursos",
    )
    statements = []
    numbers: set[int] = set()
    texts: set[str] = set()
    mapped_courses: set[str] = set()
    for location, (number, statement_text, first, second) in rows:
        if type(number) is not int or not 1 <= number <= 74 or number in numbers:
            raise CatalogError(f"{location}: número deve ser inteiro, único e entre 1 e 74.")
        statement_text = _string(statement_text, location)
        text_key = " ".join(statement_text.casefold().split())
        if text_key in texts:
            raise CatalogError(f"{location}: afirmativa duplicada.")
        _string(first, location)
        linked = []
        for label in (first, second):
            if label is None:
                continue
            label = _string(label, location)
            expanded = COURSE_LABELS.get(label, (label,))
            for name in expanded:
                if name not in courses:
                    raise CatalogError(f"{location}: rótulo de curso desconhecido: {label}.")
                if name in linked:
                    raise CatalogError(f"{location}: vínculo duplicado com {name}.")
                linked.append(name)
        numbers.add(number)
        texts.add(text_key)
        mapped_courses.update(linked)
        statements.append(StatementData(number, number, statement_text, tuple(sorted(linked))))
    if numbers != set(range(1, 75)):
        raise CatalogError(
            "Tabela_Cursos: são obrigatórias as 74 afirmativas, numeradas de 1 a 74."
        )
    if mapped_courses != set(courses):
        raise CatalogError("Todos os cursos precisam de pelo menos uma afirmativa.")
    return Catalog(
        source_sha256,
        tuple(sorted(areas.values(), key=lambda a: a.name)),
        tuple(sorted(courses.values(), key=lambda c: c.name)),
        tuple(sorted(statements, key=lambda s: s.source_number)),
    )


def _catalog_rows(catalog: Catalog, version_id: UUID) -> list[tuple[type, list[dict]]]:
    def identifier(kind: str, key: str) -> UUID:
        return uuid5(version_id, f"{kind}:{key}")

    return [
        (
            Area,
            [
                dict(
                    id=identifier("area", a.name),
                    quiz_version_id=version_id,
                    name=a.name,
                    destination=a.destination,
                    destination_instructions=PENDING_INSTRUCTIONS,
                )
                for a in catalog.areas
            ],
        ),
        (
            Course,
            [
                dict(
                    id=identifier("course", c.name),
                    quiz_version_id=version_id,
                    name=c.name,
                    area_id=identifier("area", c.area),
                    description=None,
                    destination=None,
                    destination_instructions=None,
                )
                for c in catalog.courses
            ],
        ),
        (
            Statement,
            [
                dict(
                    id=identifier("statement", str(s.source_number)),
                    quiz_version_id=version_id,
                    source_number=s.source_number,
                    display_order=s.display_order,
                    text=s.text,
                )
                for s in catalog.statements
            ],
        ),
        (
            StatementCourseWeight,
            [
                dict(
                    quiz_version_id=version_id,
                    statement_id=identifier("statement", str(s.source_number)),
                    course_id=identifier("course", course),
                    weight=1,
                )
                for s in catalog.statements
                for course in s.courses
            ],
        ),
    ]


def _matches(connection: Connection, model: type, rows: list[dict], version_id: UUID) -> bool:
    keys = list(rows[0])
    actual = connection.execute(
        select(*(getattr(model, key) for key in keys)).where(model.quiz_version_id == version_id)
    )
    return {tuple(row) for row in actual} == {tuple(row[key] for key in keys) for row in rows}


@dataclass(frozen=True)
class ImportResult:
    version_id: UUID
    version_number: int
    status: str
    created: bool


def import_catalog(
    engine: Engine, catalog: Catalog, *, version_number: int, event_name: str = "ISE Day"
) -> ImportResult:
    if type(version_number) is not int or version_number <= 0:
        raise CatalogError("A versão deve ser um inteiro positivo.")
    _string(event_name, "Nome do evento")
    # One transaction, including all catalog rows. Serializes concurrent importer runs.
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(735020251)"))
        existing = (
            connection.execute(
                select(QuizVersion)
                .where(QuizVersion.version_number == version_number)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        version_id = existing["id"] if existing else uuid4()
        version_values = dict(
            event_name=event_name,
            version_number=version_number,
            required_selection_count=25,
            scoring_method=SCORING_METHOD,
            psychology_destination=PSYCHOLOGY_DESTINATION,
            psychology_instructions=PSYCHOLOGY_INSTRUCTIONS,
        )
        tables = _catalog_rows(catalog, version_id)
        if existing:
            if any(existing[key] != value for key, value in version_values.items()) or not all(
                _matches(connection, model, rows, version_id) for model, rows in tables
            ):
                raise CatalogError(
                    f"A versão {version_number} já existe com conteúdo diferente; "
                    "use outro número de versão. Nenhum dado foi alterado."
                )
            return ImportResult(version_id, version_number, existing["status"], False)
        connection.execute(
            insert(QuizVersion).values(id=version_id, status="draft", **version_values)
        )
        for model, rows in tables:
            connection.execute(insert(model), rows)
        return ImportResult(version_id, version_number, "draft", True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("validate", "import"))
    parser.add_argument("--file", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument(
        "--report", type=Path, help="Salvar catálogo normalizado e pendências em JSON"
    )
    parser.add_argument("--version", type=int, help="Número obrigatório para importar")
    parser.add_argument("--event", default="ISE Day")
    args = parser.parse_args(argv)
    if args.action == "import" and (args.version is None or args.version <= 0):
        parser.error("import exige --version com inteiro positivo")
    if args.report and args.report.resolve() == args.file.resolve():
        parser.error("--report não pode sobrescrever a planilha de origem")
    try:
        catalog = read_catalog(args.file)
        report = catalog.report()
        if args.report:
            args.report.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        print(
            json.dumps(
                {
                    key: report[key]
                    for key in (
                        "source_sha256",
                        "counts",
                        "area_coverage",
                        "identical_course_mappings",
                        "review_notes",
                    )
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if args.action == "import":
            engine = build_engine(get_settings())
            try:
                result = import_catalog(
                    engine, catalog, version_number=args.version, event_name=args.event
                )
            finally:
                engine.dispose()
            print(json.dumps(asdict(result), default=str, ensure_ascii=False))
        return 0
    except (CatalogError, OSError, BadZipFile, InvalidFileException, KeyError) as exc:
        print(f"Erro de catálogo: {exc}", file=sys.stderr)
        return 1
    except (SQLAlchemyError, ValidationError):
        # Never echo connection URLs, parameters or credentials in CLI diagnostics.
        print(
            "Erro de banco: verifique a conexão e execute alembic upgrade head. "
            "A importação não foi concluída.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
