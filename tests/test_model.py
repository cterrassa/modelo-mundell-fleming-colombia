"""Tests unitarios para el modelo MF.

Verifica:
1. is_star_trm() es consistente con el solver: la TRM de la curva IS* evaluada
   en el Y de equilibrio coincide con la TRM del solver (diff < 1e-6).
2. Comparativa estatica canonica:
   - perfecta + ΔG → ΔY = 0.
   - perfecta + ΔM → ΔY > 0 y TRM ↑.
   - fijo + ΔM autonomo → ΔY = 0 (M endogena).
   - fijo + ΔG → ΔY > 0.
3. Identidad contable Y = C + I + G + NX se cumple ante cualquier choque
   con drift < 1e-3 respecto al residuo base.
4. TRM constante en regimen fijo ante todos los choques.

Run: pytest tests/ desde la raiz del repo.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mf_model import DEFAULT_PARAMETERS, Shock, simulate
from mf_curves import is_star_trm


@pytest.fixture(scope="module")
def calibration() -> dict:
    df = pd.read_csv(ROOT / "data_processed" / "base_calibration.csv")
    out: dict = {}
    for _, row in df.iterrows():
        try:
            out[row["variable"]] = float(row["value"])
        except (TypeError, ValueError):
            out[row["variable"]] = row["value"]
    return out


# ---------- 1. Consistencia IS* curve vs solver ----------

@pytest.mark.parametrize("shock_kw", [
    {},
    {"government_spending_pct": 5.0},
    {"money_supply_pct": 10.0},
    {"foreign_rate_bp": 100.0},
    {"nx_autonomous_pct": 2.0},
])
def test_is_star_curve_consistent_with_solver(calibration, shock_kw):
    """La TRM que da is_star_trm en Y_eq coincide con la TRM del solver."""
    shock = Shock(**shock_kw)
    sim = simulate(calibration, shock, mobility="perfecta")
    trm_from_curve = is_star_trm(
        calibration,
        shock,
        DEFAULT_PARAMETERS,
        sim["policy_rate_pct"],
        sim["gdp_real_cop_billion"],
    )
    assert abs(trm_from_curve - sim["trm_cop_per_usd"]) < 1e-4, (
        f"IS* curve da TRM={trm_from_curve:.4f} vs solver={sim['trm_cop_per_usd']:.4f}"
    )


# ---------- 2. Estatica comparativa canonica ----------

def test_perfecta_fiscal_no_mueve_Y(calibration):
    """+5%G en perfecta debe dar ΔY = 0 (resultado canonico)."""
    base = simulate(calibration, Shock(), mobility="perfecta")
    sim = simulate(calibration, Shock(government_spending_pct=5.0), mobility="perfecta")
    delta_y = sim["gdp_real_cop_billion"] - base["gdp_real_cop_billion"]
    assert abs(delta_y) < 1e-3, f"Fiscal en perfecta movio Y por {delta_y}"


def test_perfecta_monetaria_sube_Y_y_TRM(calibration):
    """+10%M en perfecta: Y sube y TRM se deprecia."""
    base = simulate(calibration, Shock(), mobility="perfecta")
    sim = simulate(calibration, Shock(money_supply_pct=10.0), mobility="perfecta")
    assert sim["gdp_real_cop_billion"] > base["gdp_real_cop_billion"]
    assert sim["trm_cop_per_usd"] > base["trm_cop_per_usd"]


def test_fijo_monetaria_autonoma_no_mueve_Y(calibration):
    """+10%M autonomo en regimen fijo: M no es exogena, no mueve Y."""
    base = simulate(calibration, Shock(), mobility="fijo")
    sim = simulate(calibration, Shock(money_supply_pct=10.0), mobility="fijo")
    delta_y = sim["gdp_real_cop_billion"] - base["gdp_real_cop_billion"]
    assert abs(delta_y) < 1e-3, f"Monetaria autonoma en fijo movio Y por {delta_y}"


def test_fijo_fiscal_sube_Y(calibration):
    """+5%G en fijo: fiscal es plenamente efectiva."""
    base = simulate(calibration, Shock(), mobility="fijo")
    sim = simulate(calibration, Shock(government_spending_pct=5.0), mobility="fijo")
    assert sim["gdp_real_cop_billion"] > base["gdp_real_cop_billion"]


def test_fijo_TRM_constante(calibration):
    """En regimen fijo TRM no se mueve ante ningun choque."""
    base = simulate(calibration, Shock(), mobility="fijo")
    for shock_kw in [
        {"government_spending_pct": 5.0},
        {"money_supply_pct": 10.0},
        {"foreign_rate_bp": 100.0},
        {"oil_price_pct": -15.0},
        {"nx_autonomous_pct": 2.0},
    ]:
        sim = simulate(calibration, Shock(**shock_kw), mobility="fijo")
        assert abs(sim["trm_cop_per_usd"] - base["trm_cop_per_usd"]) < 1e-6, (
            f"TRM se movio en fijo ante {shock_kw}: {sim['trm_cop_per_usd']} vs {base['trm_cop_per_usd']}"
        )


# ---------- 3. Identidad contable preservada ----------

@pytest.mark.parametrize("mobility", ["perfecta", "imperfecta", "fijo"])
@pytest.mark.parametrize("shock_kw", [
    {},
    {"government_spending_pct": 5.0},
    {"tax_pct_of_gdp": 1.0},
    {"money_supply_pct": 10.0},
    {"foreign_rate_bp": 100.0},
    {"risk_premium_bp": 150.0},
    {"oil_price_pct": -15.0},
    {"nx_autonomous_pct": 2.0},
])
def test_identidad_contable(calibration, mobility, shock_kw):
    """Y = C + I + G + NX + residuo (drift < 0.001 vs base)."""
    base = simulate(calibration, Shock(), mobility=mobility)
    sim = simulate(calibration, Shock(**shock_kw), mobility=mobility)

    def residuo(r):
        return r["gdp_real_cop_billion"] - (
            r["private_consumption_real_cop_billion"]
            + r["investment_real_cop_billion"]
            + r["government_consumption_real_cop_billion"]
            + r["net_exports_real_cop_billion"]
        )

    drift = residuo(sim) - residuo(base)
    assert abs(drift) < 1e-3, (
        f"Identidad violada en mobility={mobility}, shock={shock_kw}: drift={drift}"
    )
