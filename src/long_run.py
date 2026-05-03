"""Equilibrio de largo plazo de la economia abierta pequena (Mankiw cap. 6).

Este modulo NO es Mundell-Fleming. Es el complemento teorico de largo plazo:
en el LP los precios son flexibles y el producto vuelve a su nivel natural
Y_n. Sirve para contrastar pedagogicamente con los resultados de corto plazo
del modelo MF (cap. 13) implementado en mf_model.simulate().

Punto de partida (Mankiw cap. 6, economia abierta pequena, LP):

```text
Y = Y_n          (exogeno, dado por capital y trabajo)
C = C(Y_n - T)
I = I(r),  r = r* + prima de riesgo   (movilidad perfecta)
NX = Y_n - C - I - G - residuo        (identidad contable)
e ajusta para que NX(e) cumpla la igualdad anterior
```

Diferencias clave con corto plazo (Mundell-Fleming):
- Producto: Y queda fijo en Y_n; el simulador SR permite Y != Y_n.
- Politica monetaria: NEUTRAL en terminos reales. Solo mueve precios y tipo
  de cambio nominal. Real exchange rate y NX no se mueven por dM.
- Politica fiscal: misma direccion que SR perfecta (dG -> aprecia, NX cae),
  pero el mecanismo es estrictamente la identidad ahorro-inversion, no la
  curva IS desplazandose.
- Choques externos (Fed, riesgo, petroleo): mueven I (via r=r*+risk) y NX
  (via e), pero Y siempre queda en Y_n.
"""

from __future__ import annotations

from dataclasses import asdict
import math
from typing import Mapping

from mf_model import (
    DEFAULT_PARAMETERS,
    Shock,
    _baseline,
    _bp,
    _normalise_shock,
    _pct,
)


def simulate_long_run(
    calibration: Mapping[str, float],
    shock: Shock | Mapping[str, float] | None = None,
    parameters: Mapping[str, float] | None = None,
) -> dict[str, float]:
    """Equilibrio de largo plazo (Mankiw cap. 6) bajo movilidad perfecta.

    Y queda fijo en Y_n (la calibracion base). La tasa local queda anclada
    por UIP. El tipo de cambio absorbe el desbalance del bloque ahorro-
    inversion. La politica monetaria (``money_supply_pct``) es neutral en
    terminos reales y se ignora en este modelo.
    """
    params = dict(DEFAULT_PARAMETERS)
    if parameters:
        params.update(parameters)
    s = _normalise_shock(shock)
    b = _baseline(calibration)

    rate = b["rate0"] + _bp(s.foreign_rate_bp) + _bp(s.risk_premium_bp)
    rate_delta = rate - b["rate0"]

    y = b["y0"]
    delta_y_pct = 0.0

    tax_change = _pct(s.tax_pct_of_gdp) * b["y0"]
    c = b["c0"] * (1.0 + _pct(s.consumption_autonomous_pct)) + params["mpc"] * (-tax_change)
    inv = b["i0"] * (1.0 + _pct(s.investment_autonomous_pct) - params["investment_rate_sensitivity"] * rate_delta)
    g = b["g0"] * (1.0 + _pct(s.government_spending_pct))
    nx_aut = _pct(s.nx_autonomous_pct) * b["y0"]
    oil_export_boost = b["x0"] * params["eta_oil_export"] * _pct(s.oil_price_pct)
    nx_required = y - c - inv - g - b["residual0"]

    nx_endog_required = nx_required - nx_aut - oil_export_boost
    denominator = b["x0"] * params["eta_export_q"] + b["m0"] * params["eta_import_q"]
    numerator = nx_endog_required - b["nx0"]
    q_change = numerator / denominator if denominator != 0 else 0.0

    log_e_change = math.log1p(q_change) if q_change > -0.999 else -6.908
    x = b["x0"] * (1.0 + params["eta_export_q"] * q_change + params["eta_oil_export"] * _pct(s.oil_price_pct))
    m = b["m0"] * (1.0 - params["eta_import_q"] * q_change)
    nx_total = x - m + nx_aut

    e_change = math.exp(log_e_change) - 1.0
    nx_change_usd_m = (nx_total - b["nx0"]) * 1000.0 / b["e0"]
    ca = b["ca0"] + nx_change_usd_m

    return {
        "term": "largo_plazo",
        "trm_cop_per_usd": b["e0"] * math.exp(log_e_change),
        "trm_change_pct": e_change * 100.0,
        "gdp_real_cop_billion": y,
        "output_gap_pct": 0.0,
        "policy_rate_pct": rate,
        "private_consumption_real_cop_billion": c,
        "investment_real_cop_billion": inv,
        "government_consumption_real_cop_billion": g,
        "exports_real_cop_billion": x,
        "imports_real_cop_billion": m,
        "net_exports_real_cop_billion": nx_total,
        "current_account_usd_m": ca,
        "real_exchange_rate_index": b["q_index0"] * math.exp(log_e_change),
        "shock": asdict(s),
        "monetary_neutrality": (
            "La politica monetaria (M) es neutral en LR: solo afecta precios y "
            "tipo de cambio nominal, no variables reales."
        ),
    }
