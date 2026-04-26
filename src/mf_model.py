from __future__ import annotations

from dataclasses import dataclass, asdict
import math
from typing import Dict, Mapping

import pandas as pd


@dataclass
class Shock:
    government_spending_pct: float = 0.0
    tax_pct_of_gdp: float = 0.0
    money_supply_pct: float = 0.0
    domestic_policy_rate_bp: float = 0.0
    investment_pct: float = 0.0
    consumption_pct: float = 0.0
    foreign_rate_bp: float = 0.0
    risk_premium_bp: float = 0.0
    oil_price_pct: float = 0.0
    external_demand_pct: float = 0.0
    terms_of_trade_pct: float = 0.0
    capital_flow_usd_m: float = 0.0
    export_pct: float = 0.0
    import_pct: float = 0.0
    expected_depreciation_bp: float = 0.0
    reserves_intervention_usd_m: float = 0.0
    capital_mobility_scale: float = 1.0


DEFAULT_PARAMETERS: Dict[str, float] = {
    "mpc": 0.68,
    "investment_rate_sensitivity": 0.018,
    "money_rate_sensitivity": 0.08,
    "output_rate_sensitivity": 0.10,
    "eta_export_q": 0.45,
    "eta_import_q": 0.25,
    "eta_import_y": 1.35,
    "eta_export_y_star": 1.10,
    "eta_oil_export": 0.12,
    "eta_terms_export": 0.15,
    "capital_flow_sensitivity_usd_m_per_pp": 800.0,
    "exchange_rate_uip_sensitivity": 0.025,
    "exchange_rate_oil_sensitivity": -0.10,
    "exchange_rate_terms_sensitivity": -0.08,
    "exchange_rate_external_demand_sensitivity": -0.06,
    "exchange_rate_bp_sensitivity": 0.80,
    "exchange_rate_capital_flow_sensitivity": 0.50,
    "exchange_rate_reserve_sensitivity": 0.40,
}


SCENARIOS: Dict[str, Shock] = {
    "Base": Shock(),
    "Expansion fiscal": Shock(government_spending_pct=5.0),
    "Contraccion fiscal": Shock(government_spending_pct=-5.0),
    "Aumento tasa domestica": Shock(domestic_policy_rate_bp=100.0),
    "Reduccion tasa domestica": Shock(domestic_policy_rate_bp=-100.0),
    "Aumento tasa Fed": Shock(foreign_rate_bp=100.0),
    "Aumento prima de riesgo": Shock(risk_premium_bp=150.0),
    "Caida precio del petroleo": Shock(oil_price_pct=-10.0),
    "Aumento precio del petroleo": Shock(oil_price_pct=10.0),
    "Demanda externa positiva": Shock(external_demand_pct=5.0),
    "Salida subita de capitales": Shock(capital_flow_usd_m=-2500.0, risk_premium_bp=100.0),
    "Mejora terminos de intercambio": Shock(terms_of_trade_pct=5.0),
    "Deterioro cuenta corriente": Shock(export_pct=-5.0, import_pct=5.0),
}


SCENARIO_MECHANISMS: Dict[str, str] = {
    "Expansion fiscal": "Aumenta la demanda interna; bajo tipo de cambio flexible, el mayor ingreso eleva importaciones y puede deteriorar la cuenta corriente. Con alta movilidad de capitales el efecto sobre producto se modera por apreciacion cambiaria.",
    "Contraccion fiscal": "Reduce demanda interna e importaciones; tiende a mejorar el balance externo, con menor presion de depreciacion, aunque reduce producto.",
    "Aumento tasa domestica": "Eleva el diferencial de tasas a favor de Colombia y atrae capitales; el peso tiende a apreciarse en el corto plazo, todo lo demas constante.",
    "Reduccion tasa domestica": "Reduce el atractivo relativo de activos en pesos; presiona salidas de capital o menores entradas y tiende a depreciar la TRM.",
    "Aumento tasa Fed": "Aumenta el rendimiento externo y reduce el diferencial a favor de Colombia; tiende a depreciar el peso.",
    "Aumento prima de riesgo": "Exige mayor retorno para mantener activos colombianos; si la tasa local no compensa, la TRM sube.",
    "Caida precio del petroleo": "Deteriora ingresos externos de una economia exportadora de hidrocarburos; presiona depreciacion.",
    "Aumento precio del petroleo": "Mejora ingresos externos y terminos de intercambio; reduce presiones de depreciacion.",
    "Demanda externa positiva": "Aumenta exportaciones, mejora cuenta corriente y tiende a apreciar la moneda.",
    "Salida subita de capitales": "Deteriora la cuenta financiera y sube la prima de riesgo; la TRM aumenta.",
    "Mejora terminos de intercambio": "Aumenta poder de compra de exportaciones y mejora el balance externo; tiende a apreciar.",
    "Deterioro cuenta corriente": "Menores exportaciones y mayores importaciones amplian necesidades de financiamiento externo; presiona depreciacion.",
}


def _pct(value: float) -> float:
    return value / 100.0


def _bp(value: float) -> float:
    return value / 100.0


def simulate(
    calibration: Mapping[str, float],
    shock: Shock | Mapping[str, float] | None = None,
    parameters: Mapping[str, float] | None = None,
) -> Dict[str, float]:
    """Static Mundell-Fleming simulation around an observed Colombian baseline.

    Amounts in COP use COP billions. Balance-of-payments amounts use USD millions.
    Positive BP gap means surplus pressure; the exchange-rate adjustment rule maps
    surplus pressure into appreciation, i.e. lower COP/USD.
    """

    params = dict(DEFAULT_PARAMETERS)
    if parameters:
        params.update(parameters)

    if shock is None:
        shock_obj = Shock()
    elif isinstance(shock, Shock):
        shock_obj = shock
    else:
        shock_obj = Shock(**{k: float(v) for k, v in shock.items() if k in Shock.__dataclass_fields__})

    y0 = float(calibration["gdp_real_cop_billion"])
    c0 = float(calibration["private_consumption_real_cop_billion"])
    g0 = float(calibration["government_consumption_real_cop_billion"])
    i0_level = float(calibration["investment_real_cop_billion"])
    x0 = float(calibration["exports_real_cop_billion"])
    m0 = float(calibration["imports_real_cop_billion"])
    nx0 = x0 - m0
    residual0 = y0 - (c0 + g0 + i0_level + nx0)

    e0 = float(calibration["trm_cop_per_usd"])
    rate0 = float(calibration["policy_rate_pct"])
    inflation0 = float(calibration["inflation_yoy_pct"])
    foreign_rate0 = float(calibration["foreign_rate_pct"])
    risk0 = float(calibration["risk_premium_pct"])
    ca0 = float(calibration["current_account_usd_m"])
    ka0 = float(calibration["financial_account_inflow_usd_m"])
    errors0 = float(calibration.get("errors_omissions_usd_m", 0.0))
    gdp_usd_m = float(calibration["gdp_bp_reference_usd_m"])

    y = y0
    log_e_change = 0.0
    bp_gap = 0.0
    ka = ka0
    ca = ca0
    rate = rate0

    for _ in range(12):
        y_gap_pct = (y / y0 - 1.0) * 100.0
        rate = (
            rate0
            + _bp(shock_obj.domestic_policy_rate_bp)
            - params["money_rate_sensitivity"] * shock_obj.money_supply_pct
            + params["output_rate_sensitivity"] * y_gap_pct
        )
        real_rate_gap_pp = (rate - inflation0) - (rate0 - inflation0)

        foreign_rate = foreign_rate0 + _bp(shock_obj.foreign_rate_bp)
        risk = risk0 + _bp(shock_obj.risk_premium_bp)
        expected_dep_pp = _bp(shock_obj.expected_depreciation_bp)

        uip_gap_pp = (foreign_rate - foreign_rate0) + (risk - risk0) + expected_dep_pp - (rate - rate0)
        direct_e_change = (
            params["exchange_rate_uip_sensitivity"] * uip_gap_pp
            + params["exchange_rate_oil_sensitivity"] * _pct(shock_obj.oil_price_pct)
            + params["exchange_rate_terms_sensitivity"] * _pct(shock_obj.terms_of_trade_pct)
            + params["exchange_rate_external_demand_sensitivity"] * _pct(shock_obj.external_demand_pct)
            - params["exchange_rate_capital_flow_sensitivity"] * (shock_obj.capital_flow_usd_m / gdp_usd_m)
            - params["exchange_rate_reserve_sensitivity"] * (shock_obj.reserves_intervention_usd_m / gdp_usd_m)
        )

        q_change = math.exp(log_e_change) - 1.0
        x = x0 * (
            1.0
            + _pct(shock_obj.export_pct)
            + params["eta_export_q"] * q_change
            + params["eta_export_y_star"] * _pct(shock_obj.external_demand_pct)
            + params["eta_oil_export"] * _pct(shock_obj.oil_price_pct)
            + params["eta_terms_export"] * _pct(shock_obj.terms_of_trade_pct)
        )
        m = m0 * (
            1.0
            + _pct(shock_obj.import_pct)
            + params["eta_import_y"] * ((y / y0) - 1.0)
            - params["eta_import_q"] * q_change
        )
        nx = x - m

        tax_change = _pct(shock_obj.tax_pct_of_gdp) * y0
        c = c0 * (1.0 + _pct(shock_obj.consumption_pct)) + params["mpc"] * (y - y0 - tax_change)
        inv = i0_level * (
            1.0
            + _pct(shock_obj.investment_pct)
            - params["investment_rate_sensitivity"] * real_rate_gap_pp
        )
        g = g0 * (1.0 + _pct(shock_obj.government_spending_pct))
        y = c + inv + g + nx + residual0

        nx_change_usd_m = (nx - nx0) * 1000.0 / e0
        ca = ca0 + nx_change_usd_m
        ka = (
            ka0
            + shock_obj.capital_flow_usd_m
            + shock_obj.capital_mobility_scale
            * params["capital_flow_sensitivity_usd_m_per_pp"]
            * ((rate - rate0) - (foreign_rate - foreign_rate0) - (risk - risk0))
        )
        bp_gap = ca + ka + errors0

        log_e_change = direct_e_change - params["exchange_rate_bp_sensitivity"] * (bp_gap / gdp_usd_m)

    e_change = math.exp(log_e_change) - 1.0
    e = e0 * math.exp(log_e_change)
    q = float(calibration["real_exchange_rate_index"]) * math.exp(log_e_change)
    output_gap_pct = (y / y0 - 1.0) * 100.0

    return {
        "trm_cop_per_usd": e,
        "trm_change_pct": e_change * 100.0,
        "gdp_real_cop_billion": y,
        "output_gap_pct": output_gap_pct,
        "policy_rate_pct": rate,
        "exports_real_cop_billion": x,
        "imports_real_cop_billion": m,
        "net_exports_real_cop_billion": nx,
        "current_account_usd_m": ca,
        "financial_account_inflow_usd_m": ka,
        "balance_of_payments_gap_usd_m": bp_gap,
        "real_exchange_rate_index": q,
        "shock": asdict(shock_obj),
    }


def scenario_table(calibration: Mapping[str, float], parameters: Mapping[str, float] | None = None) -> pd.DataFrame:
    rows = []
    for name, shock in SCENARIOS.items():
        result = simulate(calibration, shock, parameters)
        rows.append(
            {
                "scenario": name,
                "trm_cop_per_usd": result["trm_cop_per_usd"],
                "trm_change_pct": result["trm_change_pct"],
                "gdp_real_cop_billion": result["gdp_real_cop_billion"],
                "output_gap_pct": result["output_gap_pct"],
                "current_account_usd_m": result["current_account_usd_m"],
                "financial_account_inflow_usd_m": result["financial_account_inflow_usd_m"],
                "balance_of_payments_gap_usd_m": result["balance_of_payments_gap_usd_m"],
            }
        )
    return pd.DataFrame(rows)


def validate_signs(calibration: Mapping[str, float], parameters: Mapping[str, float] | None = None) -> pd.DataFrame:
    base = simulate(calibration, Shock(), parameters)
    tests = [
        ("Subida prima de riesgo deprecia", Shock(risk_premium_bp=100), "trm_cop_per_usd", ">", base["trm_cop_per_usd"]),
        ("Subida tasa externa deprecia", Shock(foreign_rate_bp=100), "trm_cop_per_usd", ">", base["trm_cop_per_usd"]),
        ("Subida tasa domestica aprecia", Shock(domestic_policy_rate_bp=100), "trm_cop_per_usd", "<", base["trm_cop_per_usd"]),
        ("Caida petroleo deprecia", Shock(oil_price_pct=-10), "trm_cop_per_usd", ">", base["trm_cop_per_usd"]),
        ("Mejora exportaciones aprecia", Shock(export_pct=10), "trm_cop_per_usd", "<", base["trm_cop_per_usd"]),
        ("Expansion monetaria deprecia", Shock(money_supply_pct=10), "trm_cop_per_usd", ">", base["trm_cop_per_usd"]),
    ]
    rows = []
    for name, shock, metric, op, target in tests:
        value = simulate(calibration, shock, parameters)[metric]
        passed = value > target if op == ">" else value < target
        rows.append({"test": name, "metric": metric, "value": value, "condition": f"{op} {target:.4f}", "passed": passed})
    return pd.DataFrame(rows)
