from __future__ import annotations

from typing import Mapping

import pandas as pd

from mf_model import Shock


def pct(value: float) -> float:
    return value / 100.0


def bp(value: float) -> float:
    return value / 100.0


def shock_value(shock: Shock, field: str) -> float:
    return float(getattr(shock, field))


def base_components(calibration: Mapping[str, float]) -> dict[str, float]:
    y0 = float(calibration["gdp_real_cop_billion"])
    c0 = float(calibration["private_consumption_real_cop_billion"])
    g0 = float(calibration["government_consumption_real_cop_billion"])
    inv0 = float(calibration["investment_real_cop_billion"])
    x0 = float(calibration["exports_real_cop_billion"])
    m0 = float(calibration["imports_real_cop_billion"])
    nx0 = x0 - m0
    return {
        "y0": y0,
        "c0": c0,
        "g0": g0,
        "inv0": inv0,
        "x0": x0,
        "m0": m0,
        "nx0": nx0,
        "residual0": y0 - (c0 + g0 + inv0 + nx0),
        "e0": float(calibration["trm_cop_per_usd"]),
        "rate0": float(calibration["policy_rate_pct"]),
        "ca0": float(calibration["current_account_usd_m"]),
        "ka0": float(calibration["financial_account_inflow_usd_m"]),
        "errors0": float(calibration.get("errors_omissions_usd_m", 0.0)),
        "gdp_usd_m": float(calibration["gdp_bp_reference_usd_m"]),
    }


def scaled_exchange_params(params: Mapping[str, float], scale: float) -> dict[str, float]:
    out = dict(params)
    for key in [
        "exchange_rate_uip_sensitivity",
        "exchange_rate_oil_sensitivity",
        "exchange_rate_terms_sensitivity",
        "exchange_rate_external_demand_sensitivity",
        "exchange_rate_bp_sensitivity",
        "exchange_rate_capital_flow_sensitivity",
        "exchange_rate_reserve_sensitivity",
    ]:
        out[key] = out[key] * scale
    return out


def external_trade(
    calibration: Mapping[str, float],
    shock: Shock,
    params: Mapping[str, float],
    y: float,
    trm_change: float,
) -> tuple[float, float, float]:
    c = base_components(calibration)
    y0 = c["y0"]
    x = c["x0"] * (
        1.0
        + pct(shock_value(shock, "export_pct"))
        + params["eta_export_q"] * trm_change
        + params["eta_export_y_star"] * pct(shock_value(shock, "external_demand_pct"))
        + params["eta_oil_export"] * pct(shock_value(shock, "oil_price_pct"))
        + params["eta_terms_export"] * pct(shock_value(shock, "terms_of_trade_pct"))
    )
    m = c["m0"] * (
        1.0
        + pct(shock_value(shock, "import_pct"))
        + params["eta_import_y"] * ((y / y0) - 1.0)
        - params["eta_import_q"] * trm_change
    )
    return x, m, x - m


def is_rate_for_gap(
    calibration: Mapping[str, float],
    shock: Shock,
    params: Mapping[str, float],
    result: Mapping[str, float],
    gap_pct: float,
) -> float:
    c = base_components(calibration)
    y = c["y0"] * (1.0 + pct(gap_pct))
    trm_change = pct(float(result["trm_change_pct"]))
    _, _, nx = external_trade(calibration, shock, params, y, trm_change)
    tax_change = pct(shock_value(shock, "tax_pct_of_gdp")) * c["y0"]
    consumption = c["c0"] * (1.0 + pct(shock_value(shock, "consumption_pct")))
    consumption += params["mpc"] * (y - c["y0"] - tax_change)
    investment_no_rate = c["inv0"] * (1.0 + pct(shock_value(shock, "investment_pct")))
    government = c["g0"] * (1.0 + pct(shock_value(shock, "government_spending_pct")))
    demand_without_rate = consumption + investment_no_rate + government + nx + c["residual0"]
    denominator = max(c["inv0"] * params["investment_rate_sensitivity"], 1.0)
    return c["rate0"] + (demand_without_rate - y) / denominator


def lm_rate_for_gap(calibration: Mapping[str, float], shock: Shock, params: Mapping[str, float], gap_pct: float) -> float:
    c = base_components(calibration)
    return (
        c["rate0"]
        + bp(shock_value(shock, "domestic_policy_rate_bp"))
        - params["money_rate_sensitivity"] * shock_value(shock, "money_supply_pct")
        + params["output_rate_sensitivity"] * gap_pct
    )


def bp_rate_for_gap(
    calibration: Mapping[str, float],
    shock: Shock,
    params: Mapping[str, float],
    result: Mapping[str, float],
    gap_pct: float,
) -> float:
    c = base_components(calibration)
    y = c["y0"] * (1.0 + pct(gap_pct))
    trm_change = pct(float(result["trm_change_pct"]))
    _, _, nx = external_trade(calibration, shock, params, y, trm_change)
    nx_change_usd_m = (nx - c["nx0"]) * 1000.0 / c["e0"]
    current_account = c["ca0"] + nx_change_usd_m
    capital_mobility = max(shock_value(shock, "capital_mobility_scale"), 0.05)
    phi = max(capital_mobility * params["capital_flow_sensitivity_usd_m_per_pp"], 50.0)
    foreign_delta = bp(shock_value(shock, "foreign_rate_bp"))
    risk_delta = bp(shock_value(shock, "risk_premium_bp"))
    autonomous_flows = c["ka0"] + shock_value(shock, "capital_flow_usd_m") + c["errors0"]
    return c["rate0"] + foreign_delta + risk_delta - (current_account + autonomous_flows) / phi


def bp_gap_for_trm(
    calibration: Mapping[str, float],
    shock: Shock,
    params: Mapping[str, float],
    y: float,
    rate: float,
    trm: float,
) -> float:
    c = base_components(calibration)
    trm_change = (trm / c["e0"]) - 1.0
    _, _, nx = external_trade(calibration, shock, params, y, trm_change)
    nx_change_usd_m = (nx - c["nx0"]) * 1000.0 / c["e0"]
    current_account = c["ca0"] + nx_change_usd_m
    foreign_delta = bp(shock_value(shock, "foreign_rate_bp"))
    risk_delta = bp(shock_value(shock, "risk_premium_bp"))
    capital_gap = (rate - c["rate0"]) - foreign_delta - risk_delta
    capital_account = c["ka0"] + shock_value(shock, "capital_flow_usd_m")
    capital_account += shock_value(shock, "capital_mobility_scale") * params["capital_flow_sensitivity_usd_m_per_pp"] * capital_gap
    return current_account + capital_account + c["errors0"]


def gap_grid(base_result: Mapping[str, float], sim_result: Mapping[str, float]) -> list[float]:
    center_min = min(0.0, float(base_result["output_gap_pct"]), float(sim_result["output_gap_pct"]))
    center_max = max(0.0, float(base_result["output_gap_pct"]), float(sim_result["output_gap_pct"]))
    start = min(-6.0, center_min - 4.0)
    end = max(6.0, center_max + 4.0)
    step = (end - start) / 90.0
    return [start + i * step for i in range(91)]


def curve_data(
    calibration: Mapping[str, float],
    shock: Shock,
    base_params: Mapping[str, float],
    scenario_params: Mapping[str, float],
    base_result: Mapping[str, float],
    sim_result: Mapping[str, float],
    mobility: str = "perfecta",
) -> dict[str, object]:
    """Build IS, LM and BP=0 curve data on the (output gap, rate) plane.

    Under ``mobility="perfecta"`` the BP=0 curve is horizontal at the UIP rate
    (canonical MF). Under ``mobility="imperfecta"`` it is upward-sloping,
    reflecting finite capital mobility.
    """
    gaps = gap_grid(base_result, sim_result)
    bp_base_horizontal = float(base_result["policy_rate_pct"])
    bp_scenario_horizontal = float(sim_result["policy_rate_pct"])
    if mobility == "perfecta":
        bp_base = [bp_base_horizontal for _ in gaps]
        bp_scenario = [bp_scenario_horizontal for _ in gaps]
    else:
        bp_base = [bp_rate_for_gap(calibration, Shock(), base_params, base_result, g) for g in gaps]
        bp_scenario = [bp_rate_for_gap(calibration, shock, scenario_params, sim_result, g) for g in gaps]
    return {
        "gaps": gaps,
        "base": {
            "IS": [is_rate_for_gap(calibration, Shock(), base_params, base_result, g) for g in gaps],
            "LM": [lm_rate_for_gap(calibration, Shock(), base_params, g) for g in gaps],
            "BP=0": bp_base,
        },
        "scenario": {
            "IS": [is_rate_for_gap(calibration, shock, scenario_params, sim_result, g) for g in gaps],
            "LM": [lm_rate_for_gap(calibration, shock, scenario_params, g) for g in gaps],
            "BP=0": bp_scenario,
        },
    }


def exchange_pressure_data(
    calibration: Mapping[str, float],
    shock: Shock,
    base_params: Mapping[str, float],
    scenario_params: Mapping[str, float],
    base_result: Mapping[str, float],
    sim_result: Mapping[str, float],
) -> dict[str, object]:
    c = base_components(calibration)
    e0 = c["e0"]
    e_min = min(e0, float(sim_result["trm_cop_per_usd"])) * 0.86
    e_max = max(e0, float(sim_result["trm_cop_per_usd"])) * 1.14
    step = (e_max - e_min) / 90.0
    trms = [e_min + i * step for i in range(91)]
    return {
        "trms": trms,
        "base": [
            bp_gap_for_trm(calibration, Shock(), base_params, base_result["gdp_real_cop_billion"], base_result["policy_rate_pct"], e)
            for e in trms
        ],
        "scenario": [
            bp_gap_for_trm(calibration, shock, scenario_params, sim_result["gdp_real_cop_billion"], sim_result["policy_rate_pct"], e)
            for e in trms
        ],
    }


def impact_rows(calibration: Mapping[str, float], base_result: Mapping[str, float], sim_result: Mapping[str, float]) -> pd.DataFrame:
    c = base_components(calibration)
    rows = [
        ("TRM", sim_result["trm_change_pct"], "%"),
        ("PIB real", (sim_result["gdp_real_cop_billion"] / base_result["gdp_real_cop_billion"] - 1.0) * 100.0, "%"),
        ("Tasa domestica", sim_result["policy_rate_pct"] - base_result["policy_rate_pct"], "p.p."),
        (
            "Cuenta corriente",
            (sim_result["current_account_usd_m"] - base_result["current_account_usd_m"]) / c["gdp_usd_m"] * 100.0,
            "% PIB trim.",
        ),
        (
            "Cuenta financiera",
            (sim_result["financial_account_inflow_usd_m"] - base_result["financial_account_inflow_usd_m"]) / c["gdp_usd_m"] * 100.0,
            "% PIB trim.",
        ),
        (
            "Balance pagos",
            (sim_result["balance_of_payments_gap_usd_m"] - base_result["balance_of_payments_gap_usd_m"]) / c["gdp_usd_m"] * 100.0,
            "% PIB trim.",
        ),
        ("Tipo cambio real", (sim_result["real_exchange_rate_index"] / base_result["real_exchange_rate_index"] - 1.0) * 100.0, "%"),
    ]
    return pd.DataFrame(rows, columns=["variable", "impacto", "unidad"])


def trm_contribution_rows(
    calibration: Mapping[str, float],
    shock: Shock,
    scenario_params: Mapping[str, float],
    base_result: Mapping[str, float],
    sim_result: Mapping[str, float],
) -> pd.DataFrame:
    c = base_components(calibration)
    foreign_delta = bp(shock_value(shock, "foreign_rate_bp"))
    risk_delta = bp(shock_value(shock, "risk_premium_bp"))
    expected_delta = bp(shock_value(shock, "expected_depreciation_bp"))
    rate_delta = sim_result["policy_rate_pct"] - base_result["policy_rate_pct"]
    uip_gap = foreign_delta + risk_delta + expected_delta - rate_delta
    contributions = {
        "Diferencial tasas/riesgo": scenario_params["exchange_rate_uip_sensitivity"] * uip_gap * 100.0,
        "Petroleo": scenario_params["exchange_rate_oil_sensitivity"] * pct(shock_value(shock, "oil_price_pct")) * 100.0,
        "Terminos intercambio": scenario_params["exchange_rate_terms_sensitivity"] * pct(shock_value(shock, "terms_of_trade_pct")) * 100.0,
        "Demanda externa": scenario_params["exchange_rate_external_demand_sensitivity"] * pct(shock_value(shock, "external_demand_pct")) * 100.0,
        "Flujos capital directos": -scenario_params["exchange_rate_capital_flow_sensitivity"] * (shock_value(shock, "capital_flow_usd_m") / c["gdp_usd_m"]) * 100.0,
        "Reservas": -scenario_params["exchange_rate_reserve_sensitivity"] * (shock_value(shock, "reserves_intervention_usd_m") / c["gdp_usd_m"]) * 100.0,
        "Balance externo": -scenario_params["exchange_rate_bp_sensitivity"]
        * ((sim_result["balance_of_payments_gap_usd_m"] - base_result["balance_of_payments_gap_usd_m"]) / c["gdp_usd_m"])
        * 100.0,
    }
    residual = sim_result["trm_change_pct"] - sum(contributions.values())
    contributions["Interacciones del modelo"] = residual
    df = pd.DataFrame([{"factor": k, "puntos_pct_trm": v} for k, v in contributions.items()])
    return df.reindex(df["puntos_pct_trm"].abs().sort_values(ascending=True).index)


def comparison_rows(calibration: Mapping[str, float], base_result: Mapping[str, float], sim_result: Mapping[str, float]) -> pd.DataFrame:
    c = base_components(calibration)
    rows = [
        ("TRM", "COP/USD", base_result["trm_cop_per_usd"], sim_result["trm_cop_per_usd"], "Sube = depreciacion del peso; baja = apreciacion."),
        (
            "PIB real trimestral",
            "COP bn, precios 2015",
            base_result["gdp_real_cop_billion"],
            sim_result["gdp_real_cop_billion"],
            "Nivel trimestral a precios constantes de 2015; no es PIB anual.",
        ),
        ("Brecha del producto", "%", base_result["output_gap_pct"], sim_result["output_gap_pct"], "Cambio porcentual frente al nivel base calibrado."),
        ("Tasa domestica", "%", base_result["policy_rate_pct"], sim_result["policy_rate_pct"], "Tasa relevante del bloque monetario; incorpora regla simplificada."),
        ("Cuenta corriente", "USD m", base_result["current_account_usd_m"], sim_result["current_account_usd_m"], "Mejora si aumenta el saldo externo corriente."),
        (
            "Cuenta financiera",
            "USD m",
            base_result["financial_account_inflow_usd_m"],
            sim_result["financial_account_inflow_usd_m"],
            "Entrada neta positiva de capitales reduce presion depreciatoria.",
        ),
        ("Balance pagos", "USD m", base_result["balance_of_payments_gap_usd_m"], sim_result["balance_of_payments_gap_usd_m"], "Positivo = presion de apreciacion; negativo = depreciacion."),
        (
            "Balance pagos",
            "% PIB trim.",
            base_result["balance_of_payments_gap_usd_m"] / c["gdp_usd_m"] * 100.0,
            sim_result["balance_of_payments_gap_usd_m"] / c["gdp_usd_m"] * 100.0,
            "Misma informacion normalizada por PIB trimestral en USD.",
        ),
    ]
    out = []
    for variable, unit, base, sim, note in rows:
        delta = sim - base
        pct_delta = None if abs(base) < 1e-9 else (sim / base - 1.0) * 100.0
        out.append({"variable": variable, "unidad": unit, "base": base, "simulado": sim, "cambio": delta, "cambio_pct": pct_delta, "lectura": note})
    return pd.DataFrame(out)
