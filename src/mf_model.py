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


MOBILITY_OPTIONS = ("perfecta", "imperfecta")


def _pct(value: float) -> float:
    return value / 100.0


def _bp(value: float) -> float:
    return value / 100.0


def _normalise_shock(shock: Shock | Mapping[str, float] | None) -> Shock:
    if shock is None:
        return Shock()
    if isinstance(shock, Shock):
        return shock
    return Shock(**{k: float(v) for k, v in shock.items() if k in Shock.__dataclass_fields__})


def _baseline(calibration: Mapping[str, float]) -> Dict[str, float]:
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
        "e0": float(calibration["trm_cop_per_usd"]),
        "rate0": float(calibration["policy_rate_pct"]),
        "inflation0": float(calibration["inflation_yoy_pct"]),
        "foreign_rate0": float(calibration["foreign_rate_pct"]),
        "risk0": float(calibration["risk_premium_pct"]),
        "ca0": float(calibration["current_account_usd_m"]),
        "ka0": float(calibration["financial_account_inflow_usd_m"]),
        "errors0": float(calibration.get("errors_omissions_usd_m", 0.0)),
        "gdp_usd_m": float(calibration["gdp_bp_reference_usd_m"]),
        "q_index0": float(calibration["real_exchange_rate_index"]),
    }


def _result(b: Dict[str, float], shock_obj: Shock, y: float, rate: float,
            x: float, m: float, ca: float, ka: float, bp_gap: float,
            log_e_change: float) -> Dict[str, float]:
    e_change = math.exp(log_e_change) - 1.0
    return {
        "trm_cop_per_usd": b["e0"] * math.exp(log_e_change),
        "trm_change_pct": e_change * 100.0,
        "gdp_real_cop_billion": y,
        "output_gap_pct": (y / b["y0"] - 1.0) * 100.0,
        "policy_rate_pct": rate,
        "exports_real_cop_billion": x,
        "imports_real_cop_billion": m,
        "net_exports_real_cop_billion": x - m,
        "current_account_usd_m": ca,
        "financial_account_inflow_usd_m": ka,
        "balance_of_payments_gap_usd_m": bp_gap,
        "real_exchange_rate_index": b["q_index0"] * math.exp(log_e_change),
        "shock": asdict(shock_obj),
    }


def _simulate_perfect_mobility(b: Dict[str, float], s: Shock, p: Mapping[str, float]) -> Dict[str, float]:
    """Canonical Mundell-Fleming, flexible exchange rate, perfect capital mobility.

    BP curve is horizontal at r = r* + risk + expected depreciation. The central bank
    cannot set an autonomous policy rate (any deviation from r* triggers infinite
    capital flows), so `domestic_policy_rate_bp` is ignored in this regime. Output is
    determined by the inverted LM. The exchange rate adjusts so that net exports
    absorb the IS imbalance. Closed form: no iteration required.
    """
    rate = b["rate0"] + _bp(s.foreign_rate_bp) + _bp(s.risk_premium_bp) + _bp(s.expected_depreciation_bp)
    rate_delta = rate - b["rate0"]

    y_gap_pct = (rate_delta + p["money_rate_sensitivity"] * s.money_supply_pct) / p["output_rate_sensitivity"]
    y = b["y0"] * (1.0 + _pct(y_gap_pct))
    delta_y_pct = y_gap_pct / 100.0

    real_rate_gap_pp = rate_delta
    tax_change = _pct(s.tax_pct_of_gdp) * b["y0"]
    c = b["c0"] * (1.0 + _pct(s.consumption_pct)) + p["mpc"] * (y - b["y0"] - tax_change)
    inv = b["i0"] * (1.0 + _pct(s.investment_pct) - p["investment_rate_sensitivity"] * real_rate_gap_pp)
    g = b["g0"] * (1.0 + _pct(s.government_spending_pct))
    nx_required = y - c - inv - g - b["residual0"]

    a_export = (
        _pct(s.export_pct)
        + p["eta_export_y_star"] * _pct(s.external_demand_pct)
        + p["eta_oil_export"] * _pct(s.oil_price_pct)
        + p["eta_terms_export"] * _pct(s.terms_of_trade_pct)
    )
    a_import = _pct(s.import_pct)

    denominator = b["x0"] * p["eta_export_q"] + b["m0"] * p["eta_import_q"]
    numerator = (
        nx_required
        - b["nx0"]
        - b["x0"] * a_export
        + b["m0"] * a_import
        + b["m0"] * p["eta_import_y"] * delta_y_pct
    )
    q_change = numerator / denominator if denominator != 0 else 0.0

    log_e_change = math.log1p(q_change) if q_change > -0.999 else -6.908
    x = b["x0"] * (1.0 + a_export + p["eta_export_q"] * q_change)
    m = b["m0"] * (1.0 + a_import + p["eta_import_y"] * delta_y_pct - p["eta_import_q"] * q_change)

    nx_change_usd_m = ((x - m) - b["nx0"]) * 1000.0 / b["e0"]
    ca = b["ca0"] + nx_change_usd_m
    ka = -ca - b["errors0"]
    bp_gap = 0.0

    return _result(b, s, y, rate, x, m, ca, ka, bp_gap, log_e_change)


def _simulate_imperfect_mobility(b: Dict[str, float], s: Shock, p: Mapping[str, float]) -> Dict[str, float]:
    """Imperfect capital mobility: BP curve has finite slope and the exchange rate
    adjusts proportional to a residual balance-of-payments gap. The central bank
    follows a Taylor-style rule and the policy rate can deviate from r*. Solved by
    fixed-point iteration."""
    y = b["y0"]
    log_e_change = 0.0
    bp_gap = 0.0
    ka = b["ka0"]
    ca = b["ca0"]
    rate = b["rate0"]

    for _ in range(12):
        y_gap_pct = (y / b["y0"] - 1.0) * 100.0
        rate = (
            b["rate0"]
            + _bp(s.domestic_policy_rate_bp)
            - p["money_rate_sensitivity"] * s.money_supply_pct
            + p["output_rate_sensitivity"] * y_gap_pct
        )
        real_rate_gap_pp = (rate - b["inflation0"]) - (b["rate0"] - b["inflation0"])

        foreign_rate = b["foreign_rate0"] + _bp(s.foreign_rate_bp)
        risk = b["risk0"] + _bp(s.risk_premium_bp)
        expected_dep_pp = _bp(s.expected_depreciation_bp)

        uip_gap_pp = (foreign_rate - b["foreign_rate0"]) + (risk - b["risk0"]) + expected_dep_pp - (rate - b["rate0"])
        direct_e_change = (
            p["exchange_rate_uip_sensitivity"] * uip_gap_pp
            + p["exchange_rate_oil_sensitivity"] * _pct(s.oil_price_pct)
            + p["exchange_rate_terms_sensitivity"] * _pct(s.terms_of_trade_pct)
            + p["exchange_rate_external_demand_sensitivity"] * _pct(s.external_demand_pct)
            - p["exchange_rate_capital_flow_sensitivity"] * (s.capital_flow_usd_m / b["gdp_usd_m"])
            - p["exchange_rate_reserve_sensitivity"] * (s.reserves_intervention_usd_m / b["gdp_usd_m"])
        )

        q_change = math.exp(log_e_change) - 1.0
        x = b["x0"] * (
            1.0
            + _pct(s.export_pct)
            + p["eta_export_q"] * q_change
            + p["eta_export_y_star"] * _pct(s.external_demand_pct)
            + p["eta_oil_export"] * _pct(s.oil_price_pct)
            + p["eta_terms_export"] * _pct(s.terms_of_trade_pct)
        )
        m = b["m0"] * (
            1.0
            + _pct(s.import_pct)
            + p["eta_import_y"] * ((y / b["y0"]) - 1.0)
            - p["eta_import_q"] * q_change
        )
        nx = x - m

        tax_change = _pct(s.tax_pct_of_gdp) * b["y0"]
        c = b["c0"] * (1.0 + _pct(s.consumption_pct)) + p["mpc"] * (y - b["y0"] - tax_change)
        inv = b["i0"] * (1.0 + _pct(s.investment_pct) - p["investment_rate_sensitivity"] * real_rate_gap_pp)
        g = b["g0"] * (1.0 + _pct(s.government_spending_pct))
        y = c + inv + g + nx + b["residual0"]

        nx_change_usd_m = (nx - b["nx0"]) * 1000.0 / b["e0"]
        ca = b["ca0"] + nx_change_usd_m
        ka = (
            b["ka0"]
            + s.capital_flow_usd_m
            + s.capital_mobility_scale
            * p["capital_flow_sensitivity_usd_m_per_pp"]
            * ((rate - b["rate0"]) - (foreign_rate - b["foreign_rate0"]) - (risk - b["risk0"]))
        )
        bp_gap = ca + ka + b["errors0"]

        log_e_change = direct_e_change - p["exchange_rate_bp_sensitivity"] * (bp_gap / b["gdp_usd_m"])

    return _result(b, s, y, rate, x, m, ca, ka, bp_gap, log_e_change)


def simulate(
    calibration: Mapping[str, float],
    shock: Shock | Mapping[str, float] | None = None,
    parameters: Mapping[str, float] | None = None,
    mobility: str = "perfecta",
) -> Dict[str, float]:
    """Static Mundell-Fleming simulation, flexible exchange rate.

    Two modes:
    - ``mobility="perfecta"`` (default): canonical textbook (Mankiw ch. 13).
      Closed-form solution. Fiscal policy moves NX one-for-one and leaves Y
      unchanged; monetary policy is effective and depreciates the peso.
    - ``mobility="imperfecta"``: finite capital mobility with a residual
      balance-of-payments gap that drives exchange-rate adjustment. Iterative
      fixed-point solver. Calibration empirical for Colombia.

    Amounts in COP use COP billions. Balance-of-payments amounts use USD millions.
    Higher TRM = peso depreciation.
    """
    if mobility not in MOBILITY_OPTIONS:
        raise ValueError(f"mobility debe ser uno de {MOBILITY_OPTIONS}, no {mobility!r}")

    params = dict(DEFAULT_PARAMETERS)
    if parameters:
        params.update(parameters)
    shock_obj = _normalise_shock(shock)
    b = _baseline(calibration)

    if mobility == "perfecta":
        return _simulate_perfect_mobility(b, shock_obj, params)
    return _simulate_imperfect_mobility(b, shock_obj, params)


def scenario_table(
    calibration: Mapping[str, float],
    parameters: Mapping[str, float] | None = None,
    mobility: str = "perfecta",
) -> pd.DataFrame:
    rows = []
    for name, shock in SCENARIOS.items():
        result = simulate(calibration, shock, parameters, mobility=mobility)
        rows.append(
            {
                "scenario": name,
                "mobility": mobility,
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


def validate_signs(
    calibration: Mapping[str, float],
    parameters: Mapping[str, float] | None = None,
    mobility: str = "perfecta",
) -> pd.DataFrame:
    base = simulate(calibration, Shock(), parameters, mobility=mobility)

    common_tests = [
        ("Subida prima de riesgo deprecia", Shock(risk_premium_bp=100), "trm_cop_per_usd", ">", base["trm_cop_per_usd"]),
        ("Subida tasa externa deprecia", Shock(foreign_rate_bp=100), "trm_cop_per_usd", ">", base["trm_cop_per_usd"]),
        ("Caida petroleo deprecia", Shock(oil_price_pct=-10), "trm_cop_per_usd", ">", base["trm_cop_per_usd"]),
        ("Mejora exportaciones aprecia", Shock(export_pct=10), "trm_cop_per_usd", "<", base["trm_cop_per_usd"]),
        ("Expansion monetaria deprecia", Shock(money_supply_pct=10), "trm_cop_per_usd", ">", base["trm_cop_per_usd"]),
    ]

    if mobility == "perfecta":
        textbook_tests = [
            ("Expansion fiscal: Y constante", Shock(government_spending_pct=5), "gdp_real_cop_billion", "==", base["gdp_real_cop_billion"]),
            ("Expansion fiscal aprecia", Shock(government_spending_pct=5), "trm_cop_per_usd", "<", base["trm_cop_per_usd"]),
            ("Expansion monetaria sube Y", Shock(money_supply_pct=10), "gdp_real_cop_billion", ">", base["gdp_real_cop_billion"]),
        ]
        all_tests = common_tests + textbook_tests
    else:
        imperfect_tests = [
            ("Subida tasa domestica aprecia", Shock(domestic_policy_rate_bp=100), "trm_cop_per_usd", "<", base["trm_cop_per_usd"]),
            ("Expansion fiscal sube Y (movilidad imperfecta)", Shock(government_spending_pct=5), "gdp_real_cop_billion", ">", base["gdp_real_cop_billion"]),
        ]
        all_tests = common_tests + imperfect_tests

    rows = []
    for name, shock, metric, op, target in all_tests:
        value = simulate(calibration, shock, parameters, mobility=mobility)[metric]
        if op == ">":
            passed = value > target
        elif op == "<":
            passed = value < target
        else:
            passed = abs(value - target) / max(abs(target), 1.0) < 1e-6
        rows.append({
            "test": name,
            "metric": metric,
            "value": value,
            "condition": f"{op} {target:.4f}",
            "passed": passed,
            "mobility": mobility,
        })
    return pd.DataFrame(rows)
