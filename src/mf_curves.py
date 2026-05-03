"""Helpers para visualizar el equilibrio Mundell-Fleming en plano (Y, TRM).

Modelo MF para economia abierta pequena con movilidad de capitales. En este
marco:

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
    cons = c["c0"] * (1.0 + shock.consumption_autonomous_pct / 100.0) + params["mpc"] * (y_value - c["y0"] - tax_change)
    inv = c["i0"] * (1.0 + shock.investment_autonomous_pct / 100.0 - params["investment_rate_sensitivity"] * rate_delta)
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


def money_market_data(
    calibration: Mapping[str, float],
    shock: Shock,
    params: Mapping[str, float],
    base_result: Mapping[str, float],
    sim_result: Mapping[str, float],
) -> dict[str, object]:
    """Datos para el grafico del mercado monetario en el plano (M/P, r).

    M/P se normaliza con base = 1.0; un valor 1.10 significa expansion del 10%.
    Oferta: linea vertical en 1 + money_supply_pct/100.
    Demanda L(r, Y) bajo el modelo:
        rate = rate0 + d_policy - kappa_M * M_pct + kappa_Y * y_gap_pct
    Despejando M_pct dada r y Y:
        M_pct = (rate0 + d_policy - rate + kappa_Y * y_gap_pct) / kappa_M
    """
    c = base_components(calibration)
    rate0 = c["rate0"]
    kappa_M = params["money_rate_sensitivity"]
    kappa_Y = params["output_rate_sensitivity"]

    base_rate = float(base_result["policy_rate_pct"])
    sim_rate = float(sim_result["policy_rate_pct"])
    base_y_gap = float(base_result["output_gap_pct"])
    sim_y_gap = float(sim_result["output_gap_pct"])

    base_supply = 1.0  # base normalized
    sim_supply = 1.0 + shock_value(shock, "money_supply_pct") / 100.0

    r_center = (base_rate + sim_rate) / 2
    r_range = max(2.5, abs(sim_rate - base_rate) * 2.0 + 2.5)
    r_min = r_center - r_range
    r_max = r_center + r_range
    n_points = 60
    step = (r_max - r_min) / (n_points - 1)
    rates = [r_min + i * step for i in range(n_points)]

    base_d_policy = 0.0  # base shock has no policy rate change
    sim_d_policy = bp(shock_value(shock, "domestic_policy_rate_bp"))

    base_demand = [
        1.0 + ((rate0 + base_d_policy - r + kappa_Y * base_y_gap) / kappa_M) / 100.0
        for r in rates
    ]
    sim_demand = [
        1.0 + ((rate0 + sim_d_policy - r + kappa_Y * sim_y_gap) / kappa_M) / 100.0
        for r in rates
    ]

    return {
        "rates": rates,
        "base_supply": base_supply,
        "sim_supply": sim_supply,
        "base_demand": base_demand,
        "sim_demand": sim_demand,
        "base_eq": (base_supply, base_rate),
        "sim_eq": (sim_supply, sim_rate),
    }


def ad_as_data(
    calibration: Mapping[str, float],
    shock: Shock,
    params: Mapping[str, float],
    base_result: Mapping[str, float],
    sim_result: Mapping[str, float],
) -> dict[str, object]:
    """Datos para el grafico AD-AS en el plano (Y, P).

    P se normaliza con base = 1.0. AS de corto plazo es horizontal en P=1.0
    (precios fijos). AS de largo plazo es vertical en Y_n (= Y0 base).

    AD se deriva de la LM dado r anclada por UIP en el modo perfecta. Para
    cada P, M/P real = base * (M_supply / P_pct). Resuelve Y de la LM:
        Y = Y0 * (1 + (rate_delta + kappa_M * M_pct) / kappa_Y)
    Con M_pct efectivo = M_supply_pct - P_pct.
    """
    c = base_components(calibration)
    y0 = c["y0"]
    rate0 = c["rate0"]
    kappa_M = params["money_rate_sensitivity"]
    kappa_Y = params["output_rate_sensitivity"]

    base_rate = float(base_result["policy_rate_pct"])
    sim_rate = float(sim_result["policy_rate_pct"])
    rate_delta_base = base_rate - rate0
    rate_delta_sim = sim_rate - rate0

    money_pct_sim = shock_value(shock, "money_supply_pct")

    p_min, p_max = 0.85, 1.15
    n_points = 60
    step = (p_max - p_min) / (n_points - 1)
    prices = [p_min + i * step for i in range(n_points)]

    def y_at_price(p: float, rate_delta: float, m_pct_supply: float) -> float:
        p_pct = (p - 1.0) * 100.0
        m_pct_effective = m_pct_supply - p_pct
        y_gap_pct = (rate_delta + kappa_M * m_pct_effective) / kappa_Y
        return y0 * (1.0 + y_gap_pct / 100.0)

    base_ys = [y_at_price(p, 0.0, 0.0) for p in prices]
    sim_ys = [y_at_price(p, rate_delta_sim, money_pct_sim) for p in prices]

    y_n = y0  # nivel natural

    return {
        "prices": prices,
        "base_ad": base_ys,
        "sim_ad": sim_ys,
        "y_n": y_n,
        "p_base": 1.0,
        "base_eq": (y_at_price(1.0, 0.0, 0.0), 1.0),
        "sim_eq": (y_at_price(1.0, rate_delta_sim, money_pct_sim), 1.0),
    }


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
