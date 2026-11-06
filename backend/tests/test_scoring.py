from dataclasses import replace
from uuid import UUID, uuid4, uuid5

import pytest

from app.catalog import DEFAULT_WORKBOOK, read_catalog
from app.scoring import (
    AreaScore,
    CourseDefinition,
    CourseScore,
    CourseWeight,
    InvalidSelectionError,
    ScoringCatalog,
    ScoringConfigurationError,
    StatementDefinition,
    calculate_scores,
)


def identifier(number):
    return UUID(int=number)


# Three areas and six courses, including an area/course that can score zero.
AREAS = tuple(identifier(i) for i in range(1, 4))
COURSES = tuple(identifier(i) for i in range(11, 17))
STATEMENTS = tuple(identifier(i) for i in range(101, 127))


def make_catalog(links):
    """Each list item gives the course indexes and weights for one statement."""
    return ScoringCatalog(
        area_ids=AREAS,
        courses=tuple(
            CourseDefinition(course, AREAS[index // 2]) for index, course in enumerate(COURSES)
        ),
        statements=tuple(
            StatementDefinition(
                STATEMENTS[index],
                tuple(CourseWeight(COURSES[course], weight) for course, weight in weights),
            )
            for index, weights in enumerate(links)
        ),
    )


def test_distinct_area_per_statement_weighted_courses_and_zero_results():
    # All 25 statements reach two courses in the first area, one with weight 3.
    # The first statement also reaches the second area. Area scores stay unweighted.
    catalog = make_catalog([[(0, 1), (1, 3), (2, 2)]] + [[(0, 1), (1, 3)]] * 24 + [[(4, 1)]])
    result = calculate_scores(catalog, STATEMENTS[:25])
    assert result.areas == (
        AreaScore(AREAS[0], 25, True),
        AreaScore(AREAS[1], 1, False),
        AreaScore(AREAS[2], 0, False),
    )
    assert result.courses == (
        CourseScore(COURSES[0], 25, False),
        CourseScore(COURSES[1], 75, True),
        CourseScore(COURSES[2], 2, False),
        CourseScore(COURSES[3], 0, False),
        CourseScore(COURSES[4], 0, False),
        CourseScore(COURSES[5], 0, False),
    )


def test_recommend_courses_within_each_winning_area_instead_of_global_ranking():
    # Two winning areas, but the best courses have different scores (25 and 13).
    catalog = make_catalog([[(0, 1), (2, 1)]] * 13 + [[(0, 1), (3, 1)]] * 12)
    result = calculate_scores(catalog, STATEMENTS[:25])
    assert [area.area_id for area in result.areas if area.is_winner] == list(AREAS[:2])
    assert [course for course in result.courses if course.is_recommended] == [
        CourseScore(COURSES[0], 25, True),
        CourseScore(COURSES[2], 13, True),
    ]


def test_preserves_all_area_and_course_ties_without_truncation():
    catalog = make_catalog([[(index, 1) for index in range(6)]] * 25)
    result = calculate_scores(catalog, STATEMENTS[:25])
    assert result.areas == tuple(AreaScore(area, 25, True) for area in AREAS)
    assert result.courses == tuple(CourseScore(course, 25, True) for course in COURSES)


def test_course_in_losing_area_is_not_recommended_even_with_highest_course_score():
    catalog = make_catalog([[(0, 1)]] * 13 + [[(2, 100)]] * 12)
    result = calculate_scores(catalog, STATEMENTS[:25])
    assert result.areas[:2] == (AreaScore(AREAS[0], 13, True), AreaScore(AREAS[1], 12, False))
    assert result.courses[0] == CourseScore(COURSES[0], 13, True)
    assert result.courses[2] == CourseScore(COURSES[2], 1200, False)


def test_does_not_normalize_by_area_coverage():
    catalog = make_catalog([[(0, 1)]] * 13 + [[(2, 1)]] * 12 + [[(0, 1)]])
    # Coverage is 14 vs 12; raw selected counts 13 vs 12 determine the winner.
    result = calculate_scores(catalog, STATEMENTS[:25])
    assert [area.area_id for area in result.areas if area.is_winner] == [AREAS[0]]


def test_selection_and_catalog_order_do_not_change_results_or_mutate_inputs():
    catalog = make_catalog([[(0, 2), (1, 1), (2, 1)]] * 25)
    selection = list(STATEMENTS[:25])
    result = calculate_scores(catalog, selection)
    reordered = replace(
        catalog,
        area_ids=catalog.area_ids[::-1],
        courses=catalog.courses[::-1],
        statements=tuple(
            replace(statement, weights=statement.weights[::-1])
            for statement in catalog.statements[::-1]
        ),
    )
    assert calculate_scores(reordered, selection[::-1]) == result
    assert calculate_scores(catalog, selection) == result
    assert selection == list(STATEMENTS[:25])


@pytest.mark.parametrize("count", [0, 24, 26])
def test_rejects_wrong_number_of_selections(count):
    catalog = make_catalog([[(0, 1)]] * 26)
    with pytest.raises(InvalidSelectionError, match="exatamente 25"):
        calculate_scores(catalog, STATEMENTS[:count])


def test_rejects_25_choices_with_repetition():
    catalog = make_catalog([[(0, 1)]] * 25)
    with pytest.raises(InvalidSelectionError, match="únicas"):
        calculate_scores(catalog, (*STATEMENTS[:24], STATEMENTS[0]))


def test_rejects_unknown_statement():
    catalog = make_catalog([[(0, 1)]] * 25)
    with pytest.raises(InvalidSelectionError, match="inexistente"):
        calculate_scores(catalog, (*STATEMENTS[:24], uuid4()))


@pytest.mark.parametrize("weight", [0, -1, 1.5, True, "1"])
def test_rejects_nonpositive_or_noninteger_weights(weight):
    catalog = make_catalog([[(0, 1)]] * 24 + [[(0, weight)]])
    with pytest.raises(ScoringConfigurationError, match="inteiro positivo"):
        calculate_scores(catalog, STATEMENTS[:25])


@pytest.mark.parametrize("kind", ["area", "course", "statement"])
def test_rejects_duplicate_identifiers_in_catalog(kind):
    catalog = make_catalog([[(0, 1)]] * 25)
    if kind == "area":
        catalog = replace(catalog, area_ids=(*catalog.area_ids, catalog.area_ids[0]))
    elif kind == "course":
        catalog = replace(catalog, courses=(*catalog.courses, catalog.courses[0]))
    else:
        catalog = replace(catalog, statements=(*catalog.statements, catalog.statements[0]))
    with pytest.raises(ScoringConfigurationError, match="duplicados"):
        calculate_scores(catalog, STATEMENTS[:25])


@pytest.mark.parametrize("missing", ["area_ids", "courses", "statements"])
def test_rejects_empty_catalog_entities(missing):
    catalog = replace(make_catalog([[(0, 1)]] * 25), **{missing: ()})
    with pytest.raises(ScoringConfigurationError, match="precisa de"):
        calculate_scores(catalog, STATEMENTS[:25])


def test_rejects_unsupported_scoring_method():
    catalog = replace(make_catalog([[(0, 1)]] * 25), scoring_method="normalized")
    with pytest.raises(ScoringConfigurationError, match="não suportado"):
        calculate_scores(catalog, STATEMENTS[:25])


def test_rejects_course_from_unknown_area():
    catalog = make_catalog([[(0, 1)]] * 25)
    catalog = replace(
        catalog, courses=(replace(catalog.courses[0], area_id=uuid4()), *catalog.courses[1:])
    )
    with pytest.raises(ScoringConfigurationError, match="área inexistente"):
        calculate_scores(catalog, STATEMENTS[:25])


def test_rejects_link_to_unknown_course():
    catalog = make_catalog([[(0, 1)]] * 25)
    catalog = replace(
        catalog,
        statements=(
            replace(catalog.statements[0], weights=(CourseWeight(uuid4(), 1),)),
            *catalog.statements[1:],
        ),
    )
    with pytest.raises(ScoringConfigurationError, match="curso inexistente"):
        calculate_scores(catalog, STATEMENTS[:25])


def test_rejects_repeated_links_instead_of_double_counting_course_points():
    catalog = make_catalog([[(0, 1), (0, 1)]] + [[(0, 1)]] * 24)
    with pytest.raises(ScoringConfigurationError, match="Vínculo duplicado"):
        calculate_scores(catalog, STATEMENTS[:25])


@pytest.mark.parametrize("unmapped_count", [1, 26])
def test_rejects_unmapped_statements_even_when_not_selected(unmapped_count):
    catalog = make_catalog([[(0, 1)]] * (26 - unmapped_count) + [[]] * unmapped_count)
    with pytest.raises(ScoringConfigurationError, match="sem vínculo"):
        calculate_scores(catalog, STATEMENTS[:25])


@pytest.fixture(scope="module")
def workbook_catalog():
    source = read_catalog(DEFAULT_WORKBOOK)
    version_id = identifier(2000)
    areas = {area.name: uuid5(version_id, f"area:{area.name}") for area in source.areas}
    courses = {course.name: uuid5(version_id, f"course:{course.name}") for course in source.courses}
    snapshot = ScoringCatalog(
        area_ids=tuple(areas.values()),
        courses=tuple(CourseDefinition(courses[c.name], areas[c.area]) for c in source.courses),
        statements=tuple(
            StatementDefinition(
                uuid5(version_id, f"statement:{statement.source_number}"),
                tuple(CourseWeight(courses[name], 1) for name in statement.courses),
            )
            for statement in source.statements
        ),
    )
    return snapshot, areas, courses


def test_original_catalog_first_25_statements_have_known_scores(workbook_catalog):
    catalog, areas, courses = workbook_catalog
    result = calculate_scores(catalog, [statement.id for statement in catalog.statements[:25]])
    assert {area.area_id: area.score for area in result.areas} == {
        areas["Saúde"]: 11,
        areas["Engenharia"]: 3,
        areas["Negócios"]: 5,
        areas["Educação"]: 4,
        areas["Arquitetura"]: 3,
    }
    expected_courses = {
        "Administração": 2,
        "Direito": 3,
        "Engenharia de Produção": 2,
        "Engenharia Civil e Mecânica": 1,
        "Enfermagem e Fisioterapia": 8,
        "Educação Física": 3,
        "Psicologia": 0,
        "Pedagogia": 4,
        "Arquitetura e Urbanismo": 3,
    }
    assert {course.course_id: course.score for course in result.courses} == {
        courses[name]: points for name, points in expected_courses.items()
    }
    assert {area.area_id for area in result.areas if area.is_winner} == {areas["Saúde"]}
    assert {course.course_id for course in result.courses if course.is_recommended} == {
        courses["Enfermagem e Fisioterapia"],
    }


def test_grouped_courses_score_once_per_selected_statement(workbook_catalog):
    catalog, _, courses = workbook_catalog
    # Every consecutive window of 25, covering all 74 original statements.
    for start in range(50):
        selection = [statement.id for statement in catalog.statements[start : start + 25]]
        result = calculate_scores(catalog, selection)
        by_course = {course.course_id: course for course in result.courses}
        assert len(by_course) == 9
        for name in ("Enfermagem e Fisioterapia", "Engenharia Civil e Mecânica"):
            course_id = courses[name]
            expected = sum(
                any(link.course_id == course_id for link in statement.weights)
                for statement in catalog.statements[start : start + 25]
            )
            assert by_course[course_id].score == expected
