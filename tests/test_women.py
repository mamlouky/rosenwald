"""
Unit tests for the women-extraction stage.

Run:  cd copy && python -m pytest tests/ -q
These tests use small synthetic fixtures only — no external data required.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

from rosenwald.women.names import parse_name                       # noqa: E402
from rosenwald.women.detect import classify                  # noqa: E402
from rosenwald.women import build_workbook as bw                   # noqa: E402


FEM_NAMES = {"Marie", "Camille", "Jeanne", "Hélène", "Gabrielle"}


def test_parse_surname_civil():
    p = parse_name("Berline-Héring (Mme)")
    assert p.surname == "Berline-Héring"
    assert p.civil == "Mme"
    assert p.given == ""


def test_parse_civil_plus_given():
    p = parse_name("Krykous (Mme Hél.)")
    assert p.surname == "Krykous"
    assert p.civil == "Mme"
    assert p.given == "Hél"


def test_parse_given_only_no_civil():
    p = parse_name("Bénard (L.)")
    assert p.surname == "Bénard"
    assert p.civil == ""
    assert p.given == "L"


def test_parse_leading_civil():
    p = parse_name("Mme Peltier.")
    assert p.surname == "Peltier"
    assert p.civil == "Mme"


def test_parse_profession_prefix_and_streetnum():
    p = parse_name("Dr 12 Bohn (Mad.) 1912")
    assert p.surname == "Bohn"
    assert p.civil == "Mad."


def test_parse_mme_vve():
    p = parse_name("Brès (Mme Vve)")
    assert p.surname == "Brès"
    assert p.civil.startswith("Mme")


def test_detect_marker_field():
    ev = classify({"gender_marker_raw": "Mme", "full_name_raw": "Guénot"}, FEM_NAMES)
    assert ev.is_woman and ev.source == "marker_field" and ev.evidence == "Mme"


def test_detect_name_civil():
    ev = classify({"full_name_raw": "Mesnard (Mlle)"}, FEM_NAMES)
    assert ev.is_woman and ev.source == "name_civil" and ev.evidence == "Mlle"


def test_detect_first_name_lowercased():
    ev = classify({"full_name_raw": "Durand (Marie)"}, FEM_NAMES)
    assert ev.is_woman and ev.source == "first_name" and ev.evidence == "marie"


def test_detect_male_is_excluded():
    ev = classify({"full_name_raw": "Bénard (L.)", "gender_marker_raw": ""}, FEM_NAMES)
    assert not ev.is_woman


def test_detect_plain_male_name_excluded():
    ev = classify({"full_name_raw": "Doucet"}, FEM_NAMES)
    assert not ev.is_woman


def _merged(**kw):
    base = {c: "" for c in bw.MERGED_COLUMNS}
    base.update(kw)
    return base


def test_build_rows_filters_and_maps():
    rows = [
        _merged(list_type="paris_quartiers", full_name_raw="Guénot (Mme)",
                gender_marker_raw="Mme", diploma_year="1881",
                profession_section="DOCTEURS", arrondissement="1er ARRONDISSEMENT",
                quartier="DES HALLES", address_raw="J.-J. Rousseau 1",
                hours_raw="2 à 4", year="1887", pdf_page="329",
                entry_raw="Guénot (Mme), J.-J. Rousseau 1, 2 à 4."),
        _merged(list_type="paris_quartiers", full_name_raw="Doucet",   # male
                year="1887", pdf_page="329", entry_raw="Doucet, Martyrs 74."),
        _merged(list_type="specialists", full_name_raw="Brès (Mme Vve)",
                specialite="ACCOUCHEMENTS", year="1888", pdf_page="50",
                entry_raw="Brès (Mme Vve) 1875, Université 58."),
    ]
    out = bw.build_rows(rows, FEM_NAMES)
    # one woman in paris_quartiers, male excluded
    assert len(out["paris_quartiers"]) == 1
    pq = out["paris_quartiers"][0]
    cols = [h for h, _ in bw.SHEETS["paris_quartiers"][1]]
    rec = dict(zip(cols, pq))
    assert rec["Nom(s)"] == "Guénot"
    assert rec["Indicateur"] == "Mme"
    assert rec["Quartier"] == "DES HALLES"
    assert rec["Entrée brute (raw_text)"].startswith("Guénot")
    # one woman in specialists
    assert len(out["specialists"]) == 1


def test_workbook_sheet_names_and_headers(tmp_path):
    rows = [_merged(list_type="paris_quartiers", full_name_raw="X (Mme)",
                    gender_marker_raw="Mme", year="1887", pdf_page="1", entry_raw="X (Mme).")]
    out = bw.build_rows(rows, FEM_NAMES)
    p = tmp_path / "w.xlsx"
    bw.write_workbook(out, p)
    import openpyxl
    wb = openpyxl.load_workbook(p)
    assert wb.sheetnames == ["paris_quartiers", "deps_cantons", "paris_rues",
                             "seine_cantons", "specialistes", "stations_thermales",
                             "bienfaisance"]
    # headers of deps_cantons must match the reference schema (Indication, no Adresse)
    deps = [c.value for c in wb["deps_cantons"][1]]
    assert deps == [h for h, _ in bw.SHEETS["deps_cantons"][1]]
    assert "Indicateur" in deps and "Adresse" not in deps
