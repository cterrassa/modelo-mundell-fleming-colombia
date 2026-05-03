from __future__ import annotations

from dataclasses import dataclass, asdict
import math
from typing import Dict, Mapping

import pandas as pd


@dataclass
class Shock:
    """Shocks del modelo Mundell-Fleming para Colombia.

    Ocho dimensiones, todas con respaldo en Mankiw cap. 13 o relevantes para Colombia.

    Politica domestica:
    - ``government_spending_pct``: choque a G como % del G base.
    - ``tax_pct_of_gdp``: choque a impuestos como % del PIB base.
    - ``money_supply_pct``: choque a M3 como % de la base monetaria.
    - ``domestic_policy_rate_bp``: choque a la tasa Banrep, en puntos basicos.
      Bajo movilidad perfecta queda anulado por la paridad de intereses.

    Externas:
    - ``foreign_rate_bp``: choque a la tasa externa (Fed funds), en puntos basicos.
    - ``risk_premium_bp``: choque a la prima de riesgo Colombia, en puntos basicos.
    - ``oil_price_pct``: choque al precio del petroleo, en %. Para Colombia
      Brent y exportaciones estan correlacionados; ``eta_oil_export`` calibra la
      transmision a exportaciones.
    - ``nx_autonomous_pct``: choque autonomo a exportaciones netas, expresado
      como % del PIB base. Recoge terminos de intercambio, demanda externa, X/M
      directos no capturados por las palancas anteriores.
    """
    government_spending_pct: float = 0.0
    tax_pct_of_gdp: float = 0.0
    money_supply_pct: float = 0.0
    domestic_policy_rate_bp: float = 0.0
    foreign_rate_bp: float = 0.0
    risk_premium_bp: float = 0.0
    oil_price_pct: float = 0.0
    nx_autonomous_pct: float = 0.0


DEFAULT_PARAMETERS: Dict[str, float] = {
    "mpc": 0.68,
    "investment_rate_sensitivity": 0.018,
    "money_rate_sensitivity": 0.08,
    "output_rate_sensitivity": 0.10,
    "eta_export_q": 0.45,
    "eta_import_q": 0.25,
    "eta_import_y": 1.35,
    "eta_oil_export": 0.12,
    "capital_flow_sensitivity_usd_m_per_pp": 800.0,
    "exchange_rate_uip_sensitivity": 0.025,
    "exchange_rate_bp_sensitivity": 0.80,
}


SCENARIOS: Dict[str, Shock] = {
    "Base": Shock(),
    "Expansion fiscal (+5% G)": Shock(government_spending_pct=5.0),
    "Contraccion fiscal (-5% G)": Shock(government_spending_pct=-5.0),
    "Expansion monetaria (+10% M)": Shock(money_supply_pct=10.0),
    "Subida tasa Banrep (+100 pbs)": Shock(domestic_policy_rate_bp=100.0),
    "Subida tasa Fed (+100 pbs)": Shock(foreign_rate_bp=100.0),
    "Subida prima de riesgo (+150 pbs)": Shock(risk_premium_bp=150.0),
    "Caida petroleo (-15%)": Shock(oil_price_pct=-15.0),
    "Mejora externa (+2% PIB en NX)": Shock(nx_autonomous_pct=2.0),
    "Deterioro externo (-2% PIB en NX)": Shock(nx_autonomous_pct=-2.0),
}


SCENARIO_MECHANISMS: Dict[str, str] = {
    "Expansion fiscal (+5% G)": "Aumenta el gasto publico. Bajo movilidad perfecta el producto no cambia (toda la presion va al tipo de cambio); bajo movilidad imperfecta el producto sube y la TRM se aprecia parcialmente.",
    "Contraccion fiscal (-5% G)": "Reduce gasto publico. Caso simetrico al choque expansivo.",
    "Expansion monetaria (+10% M)": "Aumenta la oferta monetaria real. La tasa cae, el peso se deprecia, las exportaciones netas suben y el producto crece. Resultado canonico de Mundell-Fleming flexible.",
    "Subida tasa Banrep (+100 pbs)": "El Banco intenta restringir. Bajo movilidad perfecta el efecto se neutraliza por flujos de capital (la tasa vuelve al valor de UIP); bajo movilidad imperfecta el peso se aprecia y el producto cae.",
    "Subida tasa Fed (+100 pbs)": "Aumenta el rendimiento externo. La paridad de intereses obliga a que la tasa local suba y el peso se deprecie para mantener el equilibrio externo.",
    "Subida prima de riesgo (+150 pbs)": "Los inversionistas exigen mas retorno para mantener activos colombianos; el peso se deprecia y la tasa local sube.",
    "Caida petroleo (-15%)": "Caen exportaciones de hidrocarburos. La cuenta corriente empeora y el peso se deprecia.",
    "Mejora externa (+2% PIB en NX)": "Mejoras autonomas en terminos de intercambio o demanda externa. Aprecia el peso y mejora la cuenta corriente.",
    "Deterioro externo (-2% PIB en NX)": "Caso simetrico: deterioro de terminos de intercambio o demanda externa. Depreciacion y mayor deficit externo.",
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
    """Caso canonico Mundell-Fleming flexible con movilidad perfecta de capitales.

    BP horizontal: r = r* + risk. La autoridad monetaria local no puede fijar la
    tasa autonomamente (cualquier desviacion es arbitrada por flujos infinitos de
    capital), de modo que ``domestic_policy_rate_bp`` se ignora en este modo.
    Y queda determinado por la LM invertida; e absorbe el desbalance de la IS via
    NX. Solucion en forma cerrada.
    """
    rate = b["rate0"] + _bp(s.foreign_rate_bp) + _bp(s.risk_premium_bp)
    rate_delta = rate - b["rate0"]

    y_gap_pct = (rate_delta + p["money_rate_sensitivity"] * s.money_supply_pct) / p["output_rate_sensitivity"]
    y = b["y0"] * (1.0 + _pct(y_gap_pct))
    delta_y_pct = y_gap_pct / 100.0

    real_rate_gap_pp = rate_delta
    tax_change = _pct(s.tax_pct_of_gdp) * b["y0"]
    c = b["c0"] + p["mpc"] * (y - b["y0"] - tax_change)
    inv = b["i0"] * (1.0 - p["investment_rate_sensitivity"] * real_rate_gap_pp)
    g = b["g0"] * (1.0 + _pct(s.government_spending_pct))
    nx_aut = _pct(s.nx_autonomous_pct) * b["y0"]
    oil_export_boost = b["x0"] * p["eta_oil_export"] * _pct(s.oil_price_pct)
    nx_required = y - c - inv - g - b["residual0"]

    nx_endog_required = nx_required - nx_aut - oil_export_boost
    denominator = b["x0"] * p["eta_export_q"] + b["m0"] * p["eta_import_q"]
    numerator = nx_endog_required - b["nx0"] + b["m0"] * p["eta_import_y"] * delta_y_pct
    q_change = numerator / denominator if denominator != 0 else 0.0

    log_e_change = math.log1p(q_change) if q_change > -0.999 else -6.908
    x = b["x0"] * (1.0 + p["eta_export_q"] * q_change + p["eta_oil_export"] * _pct(s.oil_price_pct))
    m = b["m0"] * (1.0 + p["eta_import_y"] * delta_y_pct - p["eta_import_q"] * q_change)
    nx_total = x - m + nx_aut

    nx_change_usd_m = (nx_total - b["nx0"]) * 1000.0 / b["e0"]
    ca = b["ca0"] + nx_change_usd_m
    ka = -ca - b["errors0"]
    bp_gap = 0.0

    return _result(b, s, y, rate, x, m, ca, ka, bp_gap, log_e_change)


def _simulate_imperfect_mobility(b: Dict[str, float], s: Shock, p: Mapping[str, float]) -> Dict[str, float]:
    """Movilidad de capitales imperfecta: la curva BP tiene pendiente positiva,
    el banco central puede mover la tasa autonomamente y la TRM ajusta proporcional
    a un saldo residual de balanza de pagos. Resuelto por iteracion de punto fijo.
    """
    y = b["y0"]
    log_e_change = 0.0
    bp_gap = 0.0
    ka = b["ka0"]
    ca = b["ca0"]
    rate = b["rate0"]

    nx_aut = _pct(s.nx_autonomous_pct) * b["y0"]

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

        uip_gap_pp = (foreign_rate - b["foreign_rate0"]) + (risk - b["risk0"]) - (rate - b["rate0"])
        direct_e_change = p["exchange_rate_uip_sensitivity"] * uip_gap_pp

        q_change = math.exp(log_e_change) - 1.0
        x = b["x0"] * (
            1.0
            + p["eta_export_q"] * q_change
            + p["eta_oil_export"] * _pct(s.oil_price_pct)
        )
        m = b["m0"] * (1.0 + p["eta_import_y"] * ((y / b["y0"]) - 1.0) - p["eta_import_q"] * q_change)
        nx = x - m + nx_aut

        tax_change = _pct(s.tax_pct_of_gdp) * b["y0"]
        c = b["c0"] + p["mpc"] * (y - b["y0"] - tax_change)
        inv = b["i0"] * (1.0 - p["investment_rate_sensitivity"] * real_rate_gap_pp)
        g = b["g0"] * (1.0 + _pct(s.government_spending_pct))
        y = c + inv + g + nx + b["residual0"]

        nx_change_usd_m = (nx - b["nx0"]) * 1000.0 / b["e0"]
        ca = b["ca0"] + nx_change_usd_m
        ka = (
            b["ka0"]
            + p["capital_flow_sensitivity_usd_m_per_pp"]
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
    """Simulacion estatica del modelo Mundell-Fleming flexible para Colombia.

    Dos modos:
    - ``mobility="perfecta"`` (default): caso textbook (Mankiw cap. 13). La tasa
      queda anclada por UIP, la politica fiscal NO mueve el producto (todo el
      ajuste pasa por la TRM), la politica monetaria SI es efectiva. Solucion
      en forma cerrada. ``domestic_policy_rate_bp`` no tiene efecto (el banco
      central no puede desviarse de la paridad).
    - ``mobility="imperfecta"``: capitales con movilidad finita y prima de riesgo
      endogena. La politica fiscal mueve el producto, el Banrep puede fijar tasa
      autonomamente y la TRM ajusta parcialmente. Resuelto por iteracion.

    Cantidades en COP en miles de millones; saldos externos en USD millones.
    Mayor TRM = depreciacion del peso.
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
        ("Subida tasa Fed deprecia", Shock(foreign_rate_bp=100), "trm_cop_per_usd", ">", base["trm_cop_per_usd"]),
        ("Caida petroleo deprecia", Shock(oil_price_pct=-10), "trm_cop_per_usd", ">", base["trm_cop_per_usd"]),
        ("Mejora externa aprecia", Shock(nx_autonomous_pct=1.0), "trm_cop_per_usd", "<", base["trm_cop_per_usd"]),
        ("Expansion monetaria deprecia", Shock(money_supply_pct=10), "trm_cop_per_usd", ">", base["trm_cop_per_usd"]),
        ("Expansion monetaria sube Y", Shock(money_supply_pct=10), "gdp_real_cop_billion", ">", base["gdp_real_cop_billion"]),
    ]

    if mobility == "perfecta":
        textbook_tests = [
            ("Expansion fiscal: Y constante", Shock(government_spending_pct=5), "gdp_real_cop_billion", "==", base["gdp_real_cop_billion"]),
            ("Expansion fiscal aprecia", Shock(government_spending_pct=5), "trm_cop_per_usd", "<", base["trm_cop_per_usd"]),
            ("Tasa Banrep no tiene efecto en perfecta", Shock(domestic_policy_rate_bp=100), "trm_cop_per_usd", "==", base["trm_cop_per_usd"]),
        ]
        all_tests = common_tests + textbook_tests
    else:
        imperfect_tests = [
            ("Subida tasa Banrep aprecia", Shock(domestic_policy_rate_bp=100), "trm_cop_per_usd", "<", base["trm_cop_per_usd"]),
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
