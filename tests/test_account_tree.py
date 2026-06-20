"""Tests del arbol de cuentas nacionales (treemap jerarquico, src/account_tree.py)."""

import sys
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


def test_expenditure_hierarchy_structure(qdf):
    h = acct.expenditure_hierarchy(qdf, 2024)
    assert h is not None and h["children"]
    labels = {n["label"] for n in _walk(h)}
    for must in ("Consumo privado (C)", "Consumo publico (G)", "Inversion (FBK)",
                 "Exportaciones (X)", "Importaciones (M)"):
        assert must in labels, must


def test_expenditure_partial_year_returns_none(qdf):
    assert acct.expenditure_hierarchy(qdf, 2099) is None


def test_external_and_fiscal_hierarchies():
    t = m.national_accounts_tree(2026)
    ext = acct.external_hierarchy(t)
    fis = acct.fiscal_hierarchy(t)
    ext_labels = {n["label"] for n in _walk(ext)}
    assert {"Balanza comercial", "Exportaciones de bienes", "Tradicionales",
            "No tradicionales", "Importaciones", "Renta factorial",
            "Transferencias"} <= ext_labels
    fis_labels = {n["label"] for n in _walk(fis)}
    assert {"Ingreso total", "Gasto total", "Tributarios", "Intereses",
            "Gasto primario"} <= fis_labels


def _walk(node):
    yield node
    for c in node["children"]:
        yield from _walk(c)


@pytest.mark.parametrize("builder", ["exp", "ext", "fis"])
def test_treemap_branchvalues_total_consistent(qdf, builder):
    """branchvalues='total': el valor de cada padre == suma de sus hijos directos."""
    if builder == "exp":
        root = acct.expenditure_hierarchy(qdf, 2024)
    else:
        t = m.national_accounts_tree(2030)
        root = acct.external_hierarchy(t) if builder == "ext" else acct.fiscal_hierarchy(t)
    a = acct.treemap_arrays(root)
    # ids unicos
    assert len(a["ids"]) == len(set(a["ids"]))
    # todo parent (no raiz) existe como id
    idset = set(a["ids"])
    for p in a["parents"]:
        assert p == "" or p in idset
    # padre == suma de hijos directos
    val = dict(zip(a["ids"], a["values"]))
    child_sum: dict[str, float] = {}
    for cid, par in zip(a["ids"], a["parents"]):
        if par:
            child_sum[par] = child_sum.get(par, 0.0) + val[cid]
    for pid, s in child_sum.items():
        assert abs(val[pid] - s) < 1e-3, f"{pid}: {val[pid]} != suma hijos {s}"


def test_treemap_colors_match_sign(qdf):
    """Hojas positivas en verde, negativas en rojo."""
    t = m.national_accounts_tree(2026)
    a = acct.treemap_arrays(acct.external_hierarchy(t))
    idx = {lab: i for i, lab in enumerate(a["labels"])}
    assert a["colors"][idx["Tradicionales"]] == acct._C_POS_LEAF
    assert a["colors"][idx["Importaciones"]] == acct._C_NEG_LEAF


def test_treemap_root_uses_reported_net(qdf):
    """El neto de la raiz usa el saldo reportado (override), no la suma de magnitudes."""
    t = m.national_accounts_tree(2026)
    a = acct.treemap_arrays(acct.external_hierarchy(t))
    # la raiz es el primer nodo; su texto debe reflejar la cuenta corriente (~-2,2%)
    assert "-2.2%" in a["text"][0]
