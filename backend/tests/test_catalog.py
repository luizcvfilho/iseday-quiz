import json

import pytest
from openpyxl import load_workbook

from app.catalog import DEFAULT_WORKBOOK, CatalogError, main, read_catalog
from app.core.config import Settings


def test_original_catalog_and_review_snapshot():
    catalog = read_catalog(DEFAULT_WORKBOOK)
    report = catalog.report()
    assert report["counts"] == {"statements": 74, "courses": 9, "areas": 5, "links": 78}
    assert report["area_coverage"] == {
        "Saúde": 29,
        "Engenharia": 15,
        "Negócios": 16,
        "Educação": 7,
        "Arquitetura": 11,
    }
    assert report["identical_course_mappings"] == []
    assert report["course_coverage"]["Enfermagem e Fisioterapia"] == 11
    assert report["course_coverage"]["Engenharia Civil e Mecânica"] == 7
    assert catalog.statements[2].courses == ("Enfermagem e Fisioterapia",)
    assert catalog.statements[69].courses == (
        "Arquitetura e Urbanismo",
        "Engenharia Civil e Mecânica",
    )
    assert catalog.statements[28].text == 'Colcar a "mão na massa"'
    assert catalog.statements[33].text == "Usar a instuição"
    assert [s.display_order for s in catalog.statements] == list(range(1, 75))
    # The committed review artifact must describe the exact workbook and current rules.
    snapshot = DEFAULT_WORKBOOK.with_suffix(".json").read_text(encoding="utf-8")
    assert json.loads(snapshot) == json.loads(json.dumps(report))


def test_workbook_uses_the_same_grouped_course_names_in_both_sheets():
    catalog = read_catalog(DEFAULT_WORKBOOK)
    course_names = {course.name for course in catalog.courses}
    workbook = load_workbook(DEFAULT_WORKBOOK)
    try:
        area_names = [
            row[0] for row in workbook["Tabela_Area"].iter_rows(min_row=2, values_only=True)
        ]
        statement_names = {
            name
            for row in workbook["Tabela_Cursos"].iter_rows(min_row=2, values_only=True)
            for name in row[2:4]
            if name is not None
        }
        assert len(area_names) == 9
        assert set(area_names) == statement_names == course_names
    finally:
        workbook.close()


@pytest.mark.parametrize(
    ("sheet", "cell", "value", "message"),
    [
        ("Tabela_Cursos", "A3", 1, "número"),
        ("Tabela_Cursos", "A3", 2.5, "número"),
        ("Tabela_Cursos", "A3", 75, "número"),
        ("Tabela_Cursos", "B3", "Estar no controle (liderar)", "duplicada"),
        ("Tabela_Cursos", "B3", "  Correr riscos", "espaços"),
        ("Tabela_Cursos", "B3", None, "texto obrigatório"),
        ("Tabela_Cursos", "C3", None, "texto obrigatório"),
        ("Tabela_Cursos", "C3", "Curso novo", "desconhecido"),
        ("Tabela_Cursos", "D4", "Enfermagem e Fisioterapia", "vínculo duplicado"),
        ("Tabela_Cursos", "C4", "Fisioterapia", "desconhecido"),
        ("Tabela_Cursos", "C7", "Engenharia Civil", "desconhecido"),
        ("Tabela_Cursos", "B3", '=CONCAT("texto")', "fórmulas"),
        ("Tabela_Cursos", "E3", "conteúdo extra", "coluna inesperada"),
        ("Tabela_Cursos", "C1", "Outro cabeçalho", "cabeçalho"),
        ("Tabela_Area", "A3", "Enfermagem e Fisioterapia", "duplicado"),
        ("Tabela_Area", "A2", "Enfermagem", "desconhecido"),
        ("Tabela_Area", "A5", "Engenharia Mecânica", "desconhecido"),
        ("Tabela_Area", "B5", "Negócios", "divergente"),
        ("Tabela_Area", "C3", "Destino diferente", "destinos divergentes"),
    ],
)
def test_rejects_invalid_workbook(tmp_path, sheet, cell, value, message):
    workbook = load_workbook(DEFAULT_WORKBOOK)
    workbook[sheet][cell] = value
    path = tmp_path / "invalid.xlsx"
    workbook.save(path)
    workbook.close()
    with pytest.raises(CatalogError, match=message):
        read_catalog(path)


@pytest.mark.parametrize("sheet", ["Tabela_Cursos", "Tabela_Area"])
def test_rejects_missing_row_or_sheet(tmp_path, sheet):
    workbook = load_workbook(DEFAULT_WORKBOOK)
    workbook[sheet].delete_rows(2)
    path = tmp_path / "incomplete.xlsx"
    workbook.save(path)
    with pytest.raises(CatalogError):
        read_catalog(path)
    del workbook[sheet]
    workbook.save(path)
    workbook.close()
    with pytest.raises(CatalogError, match="Aba obrigatória"):
        read_catalog(path)


def test_every_course_requires_mapping(tmp_path):
    workbook = load_workbook(DEFAULT_WORKBOOK)
    sheet = workbook["Tabela_Cursos"]
    for row in sheet.iter_rows(min_row=2):
        for cell in row[2:4]:
            if cell.value == "Engenharia de Produção":
                cell.value = "Psicologia"
    path = tmp_path / "unmapped.xlsx"
    workbook.save(path)
    workbook.close()
    with pytest.raises(CatalogError, match="Todos os cursos"):
        read_catalog(path)


def test_validation_cli_needs_no_database(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    output = tmp_path / "review.json"
    assert main(["validate", "--report", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "draft"
    assert '"links": 78' in capsys.readouterr().out


def test_failed_validation_does_not_write_report(tmp_path, capsys):
    output = tmp_path / "review.json"
    assert (
        main(["validate", "--file", str(tmp_path / "missing.xlsx"), "--report", str(output)]) == 1
    )
    assert not output.exists()
    assert "Erro de catálogo" in capsys.readouterr().err


def test_report_cannot_overwrite_source():
    with pytest.raises(SystemExit) as exc:
        main(["validate", "--report", str(DEFAULT_WORKBOOK)])
    assert exc.value.code == 2


def test_invalid_database_configuration_never_prints_credentials(monkeypatch, capsys):
    def invalid_settings():
        return Settings(database_url="private-password-in-invalid-url")

    monkeypatch.setattr("app.catalog.get_settings", invalid_settings)
    assert main(["import", "--version", "1"]) == 1
    output = capsys.readouterr()
    assert "Erro de banco" in output.err
    assert "private-password" not in output.err + output.out


@pytest.mark.parametrize("version", [None, "0", "-1"])
def test_import_requires_positive_explicit_version(version):
    args = ["import"] + (["--version", version] if version is not None else [])
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2
