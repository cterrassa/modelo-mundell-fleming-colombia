"""Panel de ecuaciones de equilibrio para el modelo Mundell-Fleming.

Genera las ecuaciones simbolicas y los valores sustituidos para los casos
base e impactado. Cada ecuacion se reporta con:
- Forma simbolica.
- Valores numericos del caso base.
- Valores numericos del caso escenario.
- Cambio (delta) por componente.

Las ecuaciones cubren:
1. Identidad del gasto: Y = C + I + G + NX + residuo
2. Consumo: C = C0 (1 + a%) + mpc * (Y - T)
3. Inversion: I = I0 (1 + h%) (1 - b * (r - r0))
4. Gobierno: G = G0 (1 + dG%)
5. Exportaciones: X = X0 (1 + eta_q * q + eta_oil * oil%)
6. Importaciones: M = M0 (1 + eta_my * dY% - eta_mq * q)
7. Exportaciones netas: NX = X - M + nx_aut
8. Mercado monetario (LM): r = r0 + d_policy - kappa_M * M% + kappa_Y * gap%
9. Paridad descubierta (UIP): r = r* + prima de riesgo (en perfecta)
"""

from __future__ import annotations

from typing import Mapping

import pandas as pd

from mf_model import Shock


def shock_value(shock: Shock, field: str) -> float:
    return float(getattr(shock, field))


def _components(calibration: Mapping[str, float]) -> dict[str, float]:
    return {
        "y0": float(calibration["gdp_real_cop_billion"]),
        "c0": float(calibration["private_consumption_real_cop_billion"]),
        "g0": float(calibration["government_consumption_real_cop_billion"]),
        "i0": float(calibration["investment_real_cop_billion"]),
        "x0": float(calibration["exports_real_cop_billion"]),
        "m0": float(calibration["imports_real_cop_billion"]),
        "trm0": float(calibration["trm_cop_per_usd"]),
        "rate0": float(calibration["policy_rate_pct"]),
        "foreign_rate0": float(calibration["foreign_rate_pct"]),
        "risk0": float(calibration["risk_premium_pct"]),
    }


def _row(component: str, formula: str, base: float, sim: float, unit: str = "COP bn") -> dict[str, object]:
    delta = sim - base
    pct_change = (sim / base - 1.0) * 100.0 if abs(base) > 1e-9 else float("nan")
    return {
        "componente": component,
        "formula": formula,
        "base": base,
        "escenario": sim,
        "delta": delta,
        "delta_pct": pct_change,
        "unidad": unit,
    }


def is_identity_rows(
    base_result: Mapping[str, float],
    sim_result: Mapping[str, float],
    calibration: Mapping[str, float],
) -> pd.DataFrame:
    """Identidad Y = C + I + G + NX + residuo en base y escenario."""
    c = _components(calibration)
    rows = [
        _row("Y (PIB real)", "Y", base_result["gdp_real_cop_billion"], sim_result["gdp_real_cop_billion"]),
        _row("C (consumo privado)", "C0(1+a%) + mpc(Y-T)",
             base_result["private_consumption_real_cop_billion"],
             sim_result["private_consumption_real_cop_billion"]),
        _row("I (inversion)", "I0(1+h%)(1 - b(r-r0))",
             base_result["investment_real_cop_billion"],
             sim_result["investment_real_cop_billion"]),
        _row("G (gasto publico)", "G0(1 + dG%)",
             base_result["government_consumption_real_cop_billion"],
             sim_result["government_consumption_real_cop_billion"]),
        _row("X (exportaciones)", "X0(1 + eta_q * q + eta_oil * oil%)",
             base_result["exports_real_cop_billion"],
             sim_result["exports_real_cop_billion"]),
        _row("M (importaciones)", "M0(1 + eta_my * dY% - eta_mq * q)",
             base_result["imports_real_cop_billion"],
             sim_result["imports_real_cop_billion"]),
        _row("NX (exportaciones netas)", "X - M + nx_aut",
             base_result["net_exports_real_cop_billion"],
             sim_result["net_exports_real_cop_billion"]),
    ]
    residuo_base = base_result["gdp_real_cop_billion"] - (
        base_result["private_consumption_real_cop_billion"]
        + base_result["investment_real_cop_billion"]
        + base_result["government_consumption_real_cop_billion"]
        + base_result["net_exports_real_cop_billion"]
    )
    residuo_sim = sim_result["gdp_real_cop_billion"] - (
        sim_result["private_consumption_real_cop_billion"]
        + sim_result["investment_real_cop_billion"]
        + sim_result["government_consumption_real_cop_billion"]
        + sim_result["net_exports_real_cop_billion"]
    )
    rows.append(_row("residuo (cierre identidad)", "Y - (C+I+G+NX)", residuo_base, residuo_sim))
    return pd.DataFrame(rows)


def monetary_block_rows(
    base_result: Mapping[str, float],
    sim_result: Mapping[str, float],
    calibration: Mapping[str, float],
    shock: Shock,
    params: Mapping[str, float],
) -> pd.DataFrame:
    """Bloque monetario: tasa de interes, UIP, tasa externa."""
    c = _components(calibration)
    base_rate = float(base_result["policy_rate_pct"])
    sim_rate = float(sim_result["policy_rate_pct"])
    foreign_base = c["foreign_rate0"]
    foreign_sim = c["foreign_rate0"] + shock_value(shock, "foreign_rate_bp") / 100.0
    risk_base = c["risk0"]
    risk_sim = c["risk0"] + shock_value(shock, "risk_premium_bp") / 100.0
    rows = [
        _row("r (tasa local)", "r0 + d_policy - kM*M% + kY*gap%", base_rate, sim_rate, unit="%"),
        _row("r* (tasa externa)", "Fed funds + Δr*", foreign_base, foreign_sim, unit="%"),
        _row("prima de riesgo", "prima_base + Δrisk", risk_base, risk_sim, unit="%"),
        _row("UIP: r* + prima", "(perfecta: ancla a r local)",
             foreign_base + risk_base, foreign_sim + risk_sim, unit="%"),
    ]
    return pd.DataFrame(rows)


def external_block_rows(
    base_result: Mapping[str, float],
    sim_result: Mapping[str, float],
    calibration: Mapping[str, float],
) -> pd.DataFrame:
    """Bloque externo: TRM, cuenta corriente, cuenta financiera."""
    rows = [
        _row("TRM", "TRM0 * (1 + q)", base_result["trm_cop_per_usd"], sim_result["trm_cop_per_usd"], unit="COP/USD"),
        _row("Cuenta corriente", "CA0 + ΔNX_USD",
             base_result["current_account_usd_m"], sim_result["current_account_usd_m"], unit="USD m"),
        _row("Cuenta financiera", "KA0 + Δflujos",
             base_result["financial_account_inflow_usd_m"], sim_result["financial_account_inflow_usd_m"], unit="USD m"),
        _row("Brecha BP", "CA + KA + errores",
             base_result["balance_of_payments_gap_usd_m"], sim_result["balance_of_payments_gap_usd_m"], unit="USD m"),
    ]
    return pd.DataFrame(rows)


def identity_check(base_result: Mapping[str, float], sim_result: Mapping[str, float]) -> dict[str, float]:
    """Verifica numericamente la identidad Y = C + I + G + NX + residuo en
    el escenario simulado. Devuelve LHS, RHS y diferencia."""
    lhs = sim_result["gdp_real_cop_billion"]
    rhs_partial = (
        sim_result["private_consumption_real_cop_billion"]
        + sim_result["investment_real_cop_billion"]
        + sim_result["government_consumption_real_cop_billion"]
        + sim_result["net_exports_real_cop_billion"]
    )
    residuo = lhs - rhs_partial
    base_residuo = (
        base_result["gdp_real_cop_billion"]
        - base_result["private_consumption_real_cop_billion"]
        - base_result["investment_real_cop_billion"]
        - base_result["government_consumption_real_cop_billion"]
        - base_result["net_exports_real_cop_billion"]
    )
    return {
        "lhs": lhs,
        "rhs_no_residuo": rhs_partial,
        "residuo": residuo,
        "residuo_base": base_residuo,
        "drift": residuo - base_residuo,
    }
