"""Validate the fixed ISE Day workbook. The database catalog is installed by Alembic."""

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from app.scoring import SCORING_METHOD

EVENT_NAME = "ISE Day"
DEFAULT_WORKBOOK = Path(__file__).resolve().parents[1] / "catalog" / "quiz-final.xlsx"
PSYCHOLOGY_DESTINATION = "Estande de Psicologia — Ginásio"
PSYCHOLOGY_INSTRUCTIONS = (
    "Vá ao ginásio e visite o estande de Psicologia para conversar com a equipe "
    "sobre seus interesses e explorar outras possibilidades."
)
PENDING_INSTRUCTIONS = (
    "Referência da planilha por área; confirmar localização e encaminhamento com a instituição."
)
EXPECTED_COURSES = {
    "Enfermagem e Fisioterapia": "Saúde",
    "Educação Física": "Saúde",
    "Psicologia": "Saúde",
    "Engenharia Civil e Mecânica": "Engenharia",
    "Engenharia de Produção": "Engenharia",
    "Administração": "Negócios",
    "Direito": "Negócios",
    "Pedagogia": "Educação",
    "Arquitetura e Urbanismo": "Arquitetura",
}
REVIEW_NOTES = (
    "Catálogo fixo: textos, metodologia, pesos e destinos devem ter validação institucional.",
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
            "status": "fixed",
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
        raise CatalogError("Tabela_Area: são obrigatórios os 9 cursos e as 5 áreas do catálogo.")

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
            if label not in courses:
                raise CatalogError(f"{location}: rótulo de curso desconhecido: {label}.")
            if label in linked:
                raise CatalogError(f"{location}: vínculo duplicado com {label}.")
            linked.append(label)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("validate",))
    parser.add_argument("--file", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument(
        "--report", type=Path, help="Salvar catálogo normalizado e pendências em JSON"
    )
    args = parser.parse_args(argv)
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
        return 0
    except (CatalogError, OSError, BadZipFile, InvalidFileException, KeyError) as exc:
        print(f"Erro de catálogo: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
