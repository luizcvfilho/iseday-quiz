"""Pure scoring for a snapshot of one quiz version; no database writes or publication.

The caller builds the snapshot from the participation's version, including every
area, course and statement. UUID membership rejects unknown/other-version choices.
Results include zero scores and use UUID order, never order as a tie breaker.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

SCORING_METHOD = "area_distinct_count_course_sum_v1"
REQUIRED_SELECTION_COUNT = 25


class InvalidSelectionError(ValueError):
    """The participant must supply exactly 25 unique statements from this version."""


class ScoringConfigurationError(ValueError):
    """The catalog cannot safely produce a result using the supported method."""


@dataclass(frozen=True)
class CourseDefinition:
    id: UUID
    area_id: UUID


@dataclass(frozen=True)
class CourseWeight:
    course_id: UUID
    weight: int


@dataclass(frozen=True)
class StatementDefinition:
    id: UUID
    weights: tuple[CourseWeight, ...]


@dataclass(frozen=True)
class ScoringCatalog:
    quiz_version_id: UUID
    area_ids: tuple[UUID, ...]
    courses: tuple[CourseDefinition, ...]
    statements: tuple[StatementDefinition, ...]
    scoring_method: str = SCORING_METHOD


@dataclass(frozen=True)
class AreaScore:
    area_id: UUID
    score: int
    is_winner: bool


@dataclass(frozen=True)
class CourseScore:
    course_id: UUID
    score: int
    is_recommended: bool


@dataclass(frozen=True)
class QuizScore:
    quiz_version_id: UUID
    areas: tuple[AreaScore, ...]
    courses: tuple[CourseScore, ...]


def _validate_catalog(catalog: ScoringCatalog) -> None:
    if catalog.scoring_method != SCORING_METHOD:
        raise ScoringConfigurationError("Método de cálculo não suportado.")
    areas = set(catalog.area_ids)
    courses = {course.id: course for course in catalog.courses}
    statements = {statement.id for statement in catalog.statements}
    if not areas or not courses or not statements:
        raise ScoringConfigurationError("O catálogo precisa de áreas, cursos e afirmativas.")
    if (
        len(areas) != len(catalog.area_ids)
        or len(courses) != len(catalog.courses)
        or len(statements) != len(catalog.statements)
    ):
        raise ScoringConfigurationError("Identificadores duplicados no catálogo.")
    if any(course.area_id not in areas for course in catalog.courses):
        raise ScoringConfigurationError("Curso vinculado a uma área inexistente nesta versão.")
    for statement in catalog.statements:
        if not statement.weights:
            raise ScoringConfigurationError("Afirmativa sem vínculo com curso.")
        linked_courses = set()
        for link in statement.weights:
            if link.course_id not in courses:
                raise ScoringConfigurationError("Vínculo com curso inexistente nesta versão.")
            if link.course_id in linked_courses:
                raise ScoringConfigurationError("Vínculo duplicado entre afirmativa e curso.")
            if type(link.weight) is not int or link.weight <= 0:
                raise ScoringConfigurationError("O peso deve ser um inteiro positivo.")
            linked_courses.add(link.course_id)


def calculate_scores(catalog: ScoringCatalog, selected_statement_ids: Sequence[UUID]) -> QuizScore:
    """Count distinct areas per statement and sum course weights, preserving all ties.

    Recommend every positive top-scoring course within each winning area. Course
    scores never compete across areas. The entire snapshot is validated, including
    unselected statements; broken content must not silently yield a result.
    """
    if len(selected_statement_ids) != REQUIRED_SELECTION_COUNT:
        raise InvalidSelectionError("Selecione exatamente 25 afirmativas.")
    selected = set(selected_statement_ids)
    if len(selected) != REQUIRED_SELECTION_COUNT:
        raise InvalidSelectionError("As 25 afirmativas devem ser únicas.")
    _validate_catalog(catalog)
    statements = {statement.id: statement for statement in catalog.statements}
    if not selected <= statements.keys():
        raise InvalidSelectionError("Afirmativa inexistente ou de outra versão do quiz.")

    courses = {course.id: course for course in catalog.courses}
    area_points = dict.fromkeys(catalog.area_ids, 0)
    course_points = dict.fromkeys(courses, 0)
    for statement_id in selected:
        statement_areas = set()
        for link in statements[statement_id].weights:
            course_points[link.course_id] += link.weight
            statement_areas.add(courses[link.course_id].area_id)
        for area_id in statement_areas:
            area_points[area_id] += 1

    maximum = max(area_points.values())
    if maximum <= 0:
        raise ScoringConfigurationError("O cálculo não produziu nenhuma pontuação positiva.")
    winners = {area_id for area_id, score in area_points.items() if score == maximum}
    best_course_by_area = dict.fromkeys(catalog.area_ids, 0)
    for course_id, score in course_points.items():
        area_id = courses[course_id].area_id
        best_course_by_area[area_id] = max(best_course_by_area[area_id], score)

    return QuizScore(
        quiz_version_id=catalog.quiz_version_id,
        areas=tuple(
            AreaScore(area_id, area_points[area_id], area_id in winners)
            for area_id in sorted(area_points)
        ),
        courses=tuple(
            CourseScore(
                course_id,
                course_points[course_id],
                courses[course_id].area_id in winners
                and course_points[course_id] > 0
                and course_points[course_id] == best_course_by_area[courses[course_id].area_id],
            )
            for course_id in sorted(course_points)
        ),
    )
