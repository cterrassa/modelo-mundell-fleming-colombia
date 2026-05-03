"""Helpers para visualizar el equilibrio Mundell-Fleming en plano (Y, TRM).

Sigue Mankiw cap. 13 (modelo MF para economia abierta pequena con movilidad
de capitales). En este marco:

- La tasa local queda anclada por UIP: ``r = r* + prima de riesgo``.
- La curva ``IS*`` relaciona Y con TRM via la respuesta de NX: para cada
  nivel de producto Y, encuentra la TRM que hace cumplir
  ``Y = C(Y-T) + I(r) + G + NX(TRM, Y) + residuo``.
  Pendiente positiva en convencion colombiana: TRM mas alta (peso depreciado)
  => mas exportaciones netas => mas demanda agregada => mas Y demandado.
- La curva ``LM*`` es **vertical** en el Y consistente con el mercado
  monetario dado r y M.
- El equilibrio es la interseccion.

Para ``imperfecta`` la tasa endogenamente se desvia de UIP, asi que tanto
IS* como LM* se trazan usando la tasa que el solver encontro como
equilibrio. La diferencia con perfecta es solo la posicion de las curvas;
el plano y la convencion son iguales.
"""

from __future__ import annotations

from typing import Mapping

import pandas as pd

from mf_model import Shock


def shock_value(shock: Shock, field: str) -> float:
    return float(getattr(shock, field))


def base_components(calibration: Mapping[str, float]) -> dict[str, float]:
    """Lee niveles del calibrado base."""
    y0 = float(calibration["gdp_real_cop_billion"])
    c0 = float(calibration["private_consumption_real_cop_billion"])
    g0 = float(calibration["government_consumption_real_cop_billion"])
    i0 = float(calibration["investment_real_cop_billion"])
    x0 = float(calibration["exports_real_cop_billion"])
    m0 = float(calibration["imports_real_cop_billion"])
    return {
        "y0": y0,
        "c0": c0,
        "g0": g0,
        "i0": i0,
        "x0": x0,
        "m0": m0,
        "nx0": x0 - m0,
        "residual0": y0 - (c0 + g0 + i0 + (x0 - m0)),
        "trm0": float(calibration["trm_cop_per_usd"]),
        "rate0": float(calibration["policy_rate_pct"]),
        "gdp_usd_m": float(calibration["gdp_bp_reference_usd_m"]),
    }


def is_star_trm(
    calibration: Mapping[str, float],
    shock: Shock,
    params: Mapping[str, float],
    rate: float,
    y_value: float,
) -> float:
    """TRM que hace cumplir la IS para el Y y r dados (curva IS*).

    Despeja ``q = TRM/TRM0 - 1`` desde la identidad
    ``Y = C(Y-T) + I(r) + G + NX(TRM, Y) + residuo``.
    """
    c = base_components(calibration)
    rate_delta = rate - c["rate0"]

    tax_change = (shock.tax_pct_of_gdp / 100.0) * c["y0"]
    cons = c["c0"] + params["mpc"] * (y_value - c["y0"] - tax_change)
    inv = c["i0"] * (1.0 - params["investment_rate_sensitivity"] * rate_delta)
    gov = c["g0"] * (1.0 + shock.government_spending_pct / 100.0)
    nx_aut = (shock.nx_autonomous_pct / 100.0) * c["y0"]
    oil_boost = c["x0"] * params["eta_oil_export"] * (shock.oil_price_pct / 100.0)

    nx_required = y_value - cons - inv - gov - c["residual0"]

    delta_y_frac = (y_value - c["y0"]) / c["y0"]
    rhs_const = c["nx0"] + oil_boost - c["m0"] * params["eta_import_y"] * delta_y_frac + nx_aut
    coef = c["x0"] * params["eta_export_q"] + c["m0"] * params["eta_import_q"]

    if abs(coef) < 1e-9:
        return c["trm0"]

    q = (nx_required - rhs_const) / coef
    return c["trm0"] * (1.0 + q)


def is_star_curve(
    calibration: Mapping[str, float],
    shock: Shock,
    params: Mapping[str, float],
    rate: float,
    y_min: float,
    y_max: float,
    n_points: int = 80,
) -> tuple[list[float], list[float]]:
    """Genera puntos (Y, TRM) para dibujar la curva IS* en el rango dado."""
    if n_points < 2:
        n_points = 2
    step = (y_max - y_min) / (n_points - 1)
    ys = [y_min + i * step for i in range(n_points)]
    trms = [is_star_trm(calibration, shock, params, rate, y) for y in ys]
    return ys, trms


def impact_rows(
    calibration: Mapping[str, float],
    base_result: Mapping[str, float],
    sim_result: Mapping[str, float],
) -> pd.DataFrame:
    """Tabla de impactos por variable para el bar chart del tab Impacto."""
    c = base_components(calibration)
    rows = [
        ("TRM", float(sim_result["trm_change_pct"]), "%"),
        ("PIB real", (float(sim_result["gdp_real_cop_billion"]) / float(base_result["gdp_real_cop_billion"]) - 1.0) * 100.0, "%"),
        ("Tasa domestica", float(sim_result["policy_rate_pct"]) - float(base_result["policy_rate_pct"]), "p.p."),
        (
            "Cuenta corriente",
            (float(sim_result["current_account_usd_m"]) - float(base_result["current_account_usd_m"])) / c["gdp_usd_m"] * 100.0,
            "% PIB trim.",
        ),
        (
            "Tipo cambio real",
            (float(sim_result["real_exchange_rate_index"]) / float(base_result["real_exchange_rate_index"]) - 1.0) * 100.0,
            "%",
        ),
    ]
    return pd.DataFrame(rows, columns=["variable", "impacto", "unidad"])


def comparison_rows(
    calibration: Mapping[str, float],
    base_result: Mapping[str, float],
    sim_result: Mapping[str, float],
) -> pd.DataFrame:
    """Tabla legible para el tab Base vs simulado."""
    c = base_components(calibration)
    rows = [
        ("TRM", "COP/USD", base_result["trm_cop_per_usd"], sim_result["trm_cop_per_usd"], "Sube = peso depreciado."),
        (
            "PIB real trimestral",
            "COP bn, precios 2015",
            base_result["gdp_real_cop_billion"],
            sim_result["gdp_real_cop_billion"],
            "Nivel trimestral; no es PIB anual.",
        ),
        (
            "Brecha del producto",
            "%",
            base_result["output_gap_pct"],
            sim_result["output_gap_pct"],
            "Cambio % frente al nivel base.",
        ),
        (
            "Tasa domestica",
            "%",
            base_result["policy_rate_pct"],
            sim_result["policy_rate_pct"],
            "Anclada por UIP en perfecta; endogena en imperfecta.",
        ),
        (
            "Cuenta corriente",
            "USD m",
            base_result["current_account_usd_m"],
            sim_result["current_account_usd_m"],
            "Mejora si aumenta el saldo externo corriente.",
        ),
    ]
    out = []
    for variable, unit, base, sim, note in rows:
        delta = sim - base
        pct_delta = None if abs(base) < 1e-9 else (sim / base - 1.0) * 100.0
        out.append(
            {
                "variable": variable,
                "unidad": unit,
                "base": base,
                "simulado": sim,
                "cambio": delta,
                "cambio_pct": pct_delta,
                "lectura": note,
            }
        )
    return pd.DataFrame(out)
