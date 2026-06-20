"""Tests de la senda oficial MFMP 2026 (src/mfmp_official.py).

Verifica:
- Las identidades contables cierran dentro de la tolerancia de redondeo del MFMP
  (cada linea se reporta a 1 decimal, asi que un saldo = diferencia de dos lineas
  redondeadas puede desviarse hasta ~0,15pp).
- El CSV comprometido coincide con build_dataframe() (golden / reproducibilidad).
- projection_path entrega el quinquenio correcto.
- national_accounts_tree expone las dos ramas con magnitudes consistentes.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import mfmp_official as m

# Tolerancia: el MFMP redondea cada linea a 1 decimal de forma independiente.
TOL = 0.15


@pytest.fixture(scope="module")
def df() -> pd.DataFrame:
    return m.build_dataframe()


def test_coverage_2025_2037(df):
    assert list(df["year"]) == list(range(2025, 2038))
    assert len(df) == 13


def test_current_account_identity_closes(df):
    """CC = trad + no_trad + importaciones + renta + transferencias + servicios."""
    for _, r in df.iterrows():
        s = (r.ca_traditional_exports_pct_gdp + r.ca_nontraditional_exports_pct_gdp
             + r.ca_goods_imports_pct_gdp + r.ca_factor_income_pct_gdp
             + r.ca_transfers_pct_gdp + r.ca_services_pct_gdp)
        assert abs(s - r.current_account_pct_gdp) <= 0.051, f"CC {int(r.year)}: {s:.2f} vs {r.current_account_pct_gdp}"


def test_fiscal_balance_identity(df):
    """Balance total = Ingreso - Gasto (tol. redondeo MFMP)."""
    for _, r in df.iterrows():
        bal = r.gnc_revenue_pct_gdp - r.gnc_expense_pct_gdp
        assert abs(bal - r.gnc_fiscal_balance_pct_gdp) <= TOL, f"Bal {int(r.year)}"


def test_primary_balance_identity(df):
    """Balance primario = Balance total + Intereses (tol. redondeo MFMP)."""
    for _, r in df.iterrows():
        prim = r.gnc_fiscal_balance_pct_gdp + r.gnc_interest_pct_gdp
        assert abs(prim - r.gnc_primary_balance_pct_gdp) <= TOL, f"Prim {int(r.year)}"


def test_revenue_components_sum(df):
    """Ingreso total = tributarios + no trib + fondos + capital + ajuste (tol.)."""
    for _, r in df.iterrows():
        rev = (r.gnc_tax_revenue_pct_gdp + r.gnc_nontax_revenue_pct_gdp
               + r.gnc_special_funds_pct_gdp + r.gnc_capital_revenue_pct_gdp
               + r.gnc_required_adjustment_pct_gdp)
        assert abs(rev - r.gnc_revenue_pct_gdp) <= TOL, f"Rev {int(r.year)}"


def test_trade_balance_derivation(df):
    """Balanza comercial = exportaciones de bienes + importaciones (signo negativo)."""
    for _, r in df.iterrows():
        tb = r.ca_goods_exports_pct_gdp + r.ca_goods_imports_pct_gdp
        assert abs(tb - r.ca_trade_balance_pct_gdp) <= 0.051


def test_nominal_gdp_anchor_and_chain(df):
    """PIB nominal 2026 anclado ~2.016 bn y encadenado con crecimiento nominal."""
    g2026 = float(df[df.year == 2026]["nominal_gdp_cop_billion"].iloc[0])
    assert abs(g2026 - 2016.0) < 1.0
    # 2027 = 2026 * (1 + 5.8/100)
    g2027 = float(df[df.year == 2027]["nominal_gdp_cop_billion"].iloc[0])
    assert abs(g2027 - g2026 * 1.058) < 1.0


def test_official_trm_path(df):
    """La TRM oficial del MFMP es creciente 2027-2037 y arranca en 3.757 en 2026."""
    assert int(df[df.year == 2026]["trm_average"].iloc[0]) == 3757
    trm = df[df.year >= 2027].sort_values("year")["trm_average"].tolist()
    assert all(b > a for a, b in zip(trm, trm[1:])), "TRM no monotona creciente desde 2027"


def test_projection_path_quinquennium():
    q = m.projection_path(base_year=2025, horizon=5)
    assert list(q["year"]) == [2026, 2027, 2028, 2029, 2030]


def test_tree_external_branch_values():
    t = m.national_accounts_tree(2026)
    labels = {n["label"].strip() for n in t["external"]}
    assert "Cuenta corriente" in labels
    assert "Balanza comercial (bienes)" in labels
    cc = next(n for n in t["external"] if n["label"] == "Cuenta corriente")
    # CC 2026 = -2,2% del PIB ~ -44 bn COP ~ -11.800 USD m
    assert abs(cc["value_pct"] - (-2.2)) < 0.05
    assert cc["value_cop_billion"] < 0
    assert cc["value_usd_m"] < 0


def test_tree_fiscal_branch_values():
    t = m.national_accounts_tree(2030)
    bal = next(n for n in t["fiscal"] if n["label"] == "Balance fiscal total (GNC)")
    assert abs(bal["value_pct"] - (-3.1)) < 0.05
    assert t["financial_account_pct_gdp"] == pytest.approx(2.4, abs=0.05)


@pytest.mark.parametrize("year", [2026, 2030, 2037])
def test_icicle_leaves_close_to_balances(year):
    """Las hojas (creditos - debitos) del icicle reproducen los saldos netos."""
    t = m.national_accounts_tree(year)
    cc = next(n for n in t["external"] if n["label"] == "Cuenta corriente")["value_pct"]
    bal = next(n for n in t["fiscal"] if n["label"] == "Balance fiscal total (GNC)")["value_pct"]
    ext_net = sum(n["value_pct"] for n in t["external_leaves"])
    fis_net = sum(n["value_pct"] for n in t["fiscal_leaves"])
    assert abs(ext_net - cc) <= 0.051, f"externo {year}: {ext_net:.2f} vs {cc}"
    assert abs(fis_net - bal) <= TOL, f"fiscal {year}: {fis_net:.2f} vs {bal}"
    # Cada hoja trae kind credito/debito coherente con su signo (salvo servicios~0).
    for n in t["external_leaves"] + t["fiscal_leaves"]:
        if abs(n["value_pct"]) < 0.05:
            continue
        if n["kind"] == "ingreso":
            assert n["value_pct"] > 0, f"{n['label']} marcado ingreso pero negativo"
        else:
            assert n["value_pct"] < 0, f"{n['label']} marcado egreso pero positivo"


def test_csv_matches_builder():
    """El CSV comprometido coincide con build_dataframe() (reproducibilidad)."""
    committed = pd.read_csv(ROOT / "data_processed" / "mfmp_2026_oficial.csv")
    built = m.build_dataframe()
    assert list(committed.columns) == list(built.columns)
    pd.testing.assert_frame_equal(
        committed.reset_index(drop=True), built.reset_index(drop=True),
        check_dtype=False, atol=1e-6,
    )
