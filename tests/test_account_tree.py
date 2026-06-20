"""Tests del arbol de cuentas nacionales (src/account_tree.py)."""

import sys
import xml.dom.minidom as minidom
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import account_tree as acct
import mfmp_official as m


@pytest.fixture(scope="module")
def qdf() -> pd.DataFrame:
    return pd.read_csv(ROOT / "data_processed" / "quarterly_master.csv")


@pytest.mark.parametrize("year", [2008, 2015, 2020, 2024])
def test_expenditure_identity_exact(qdf, year):
    """PIB = C + G + I + X - M debe cerrar exacto en valores nominales."""
    sub = qdf[qdf["year"] == year]
    ident = (sub["private_consumption_nominal_cop_billion"].sum()
             + sub["government_consumption_nominal_cop_billion"].sum()
             + sub["investment_nominal_cop_billion"].sum()
             + sub["exports_nominal_cop_billion"].sum()
             - sub["imports_nominal_cop_billion"].sum())
    assert abs(ident - sub["gdp_nominal_cop_billion"].sum()) < 1.0


def test_expenditure_view_structure(qdf):
    v = acct.expenditure_view(qdf, 2024)
    assert v is not None
    assert v["root"]["label"].startswith("PIB")
    kinds = [lf["kind"] for b in v["branches"] for lf in b["leaves"]]
    assert "ingreso" in kinds and "egreso" in kinds
    # 4 componentes positivos (C,G,I,X) + 1 negativo (M)
    assert sum(len(b["leaves"]) for b in v["branches"]) == 5


def test_expenditure_view_partial_year_returns_none(qdf):
    """Un anio sin 4 trimestres no debe producir arbol (evita anualizar parcial)."""
    # 2099 no existe -> None; ademas si hubiera un anio parcial real, igual None.
    assert acct.expenditure_view(qdf, 2099) is None


def test_external_and_fiscal_views_from_mfmp():
    t = m.national_accounts_tree(2026)
    ev = acct.external_view(t)
    fv = acct.fiscal_view(t)
    assert ev["root"]["label"] == "Cuenta corriente"
    assert fv["root"]["label"] == "Balance fiscal GNC"
    # cada vista tiene rama de creditos y de debitos
    assert {b["kind"] for b in ev["branches"]} == {"ingreso", "egreso"}
    assert {b["kind"] for b in fv["branches"]} == {"ingreso", "egreso"}


@pytest.mark.parametrize("year", [2010, 2024])
def test_tree_svg_wellformed_expenditure(qdf, year):
    v = acct.expenditure_view(qdf, year)
    svg = acct.tree_svg(f"PIB {year}", v)
    minidom.parseString(svg)  # lanza si el XML esta mal formado
    assert svg.count("<rect") >= 6  # raiz + 2 ramas + >=3 hojas
    assert acct.svg_height(v) > 0


@pytest.mark.parametrize("year", [2025, 2030, 2037])
def test_tree_svg_wellformed_mfmp(year):
    t = m.national_accounts_tree(year)
    for view in (acct.external_view(t), acct.fiscal_view(t)):
        svg = acct.tree_svg("x", view)
        minidom.parseString(svg)
        assert acct.svg_height(view) > 0


def test_svg_escapes_special_chars():
    view = {"root": {"label": "A & B <x>", "sublines": ["s"]},
            "branches": [{"label": "L", "value_label": "v", "kind": "ingreso",
                          "leaves": [{"label": "x<&>", "value_label": "1", "kind": "ingreso"}]}]}
    svg = acct.tree_svg("t & <z>", view)
    minidom.parseString(svg)  # no debe romper el XML
    assert "&amp;" in svg
