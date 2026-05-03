"""Proyeccion deterministica a 5 anos del modelo Mundell-Fleming.

Cada periodo (anual) recibe un choque de exogenas y se resuelve el equilibrio
estatico-comparativo. No hay Monte Carlo, no hay bandas estocasticas: la
proyeccion es la solucion del modelo dado el camino de las exogenas.

Las exogenas que el usuario puede mover por anio:
- gasto publico G (% del G base)
- impuestos T (% del PIB base)
- M3 (% de la base monetaria)
- tasa Banrep (puntos basicos)
- tasa Fed (puntos basicos)
- prima de riesgo Colombia (puntos basicos)
- precio Brent (%)
- NX autonomo (% del PIB base)

Las "alternativas" predefinidas son sendas constantes durante 5 anios que
ilustran un escenario macroeconomico relevante para Colombia.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import pandas as pd

from mf_model import Shock, simulate


HORIZON_YEARS = 5


@dataclass
class ProjectionScenario:
    """Senda de choques (uno por anio) durante el horizonte de 5 anios."""
    name: str
    description: str
    annual_shocks: list[Shock] = field(default_factory=list)


def _const_path(shock: Shock) -> list[Shock]:
    """Repite el mismo choque cada anio del horizonte."""
    return [Shock(**{f: getattr(shock, f) for f in Shock.__dataclass_fields__}) for _ in range(HORIZON_YEARS)]


PROJECTION_SCENARIOS: dict[str, ProjectionScenario] = {
    "Base (sin choques)": ProjectionScenario(
        name="Base (sin choques)",
        description="Las exogenas se mantienen en su valor del calibrado base. Sirve como referencia.",
        annual_shocks=_const_path(Shock()),
    ),
    "Expansion fiscal sostenida": ProjectionScenario(
        name="Expansion fiscal sostenida",
        description="Gasto publico +5% por encima del nivel base durante 5 anios.",
        annual_shocks=_const_path(Shock(government_spending_pct=5.0)),
    ),
    "Subida tasa Fed sostenida": ProjectionScenario(
        name="Subida tasa Fed sostenida",
        description="Tasa Fed +200 pbs por encima del nivel base durante 5 anios. Stress de financiamiento externo.",
        annual_shocks=_const_path(Shock(foreign_rate_bp=200.0)),
    ),
    "Ciclo petrolero adverso": ProjectionScenario(
        name="Ciclo petrolero adverso",
        description="Precio Brent -20% durante 5 anios.",
        annual_shocks=_const_path(Shock(oil_price_pct=-20.0)),
    ),
    "Subida prima de riesgo": ProjectionScenario(
        name="Subida prima de riesgo",
        description="Prima de riesgo Colombia +200 pbs sostenida durante 5 anios.",
        annual_shocks=_const_path(Shock(risk_premium_bp=200.0)),
    ),
}


def project(
    calibration: Mapping[str, float],
    annual_shocks: list[Shock | Mapping[str, float] | None],
    parameters: Mapping[str, float] | None = None,
    mobility: str = "perfecta",
    base_year: int | None = None,
) -> pd.DataFrame:
    """Devuelve un DataFrame con un trimestre/anio por fila, columnas con los
    niveles del estado simulado.

    ``annual_shocks`` debe tener exactamente 5 elementos (uno por anio).
    ``base_year`` etiqueta las filas como base_year+1, base_year+2, ... Si es
    None, usa indices relativos.
    """
    if len(annual_shocks) != HORIZON_YEARS:
        raise ValueError(f"annual_shocks debe tener {HORIZON_YEARS} elementos, no {len(annual_shocks)}.")

    rows = []
    for offset, shock in enumerate(annual_shocks, start=1):
        result = simulate(calibration, shock, parameters, mobility=mobility)
        year_label = f"{base_year + offset}p" if base_year is not None else f"+{offset}a"
        rows.append({
            "year": year_label,
            "year_offset": offset,
            "gdp_real_cop_billion": result["gdp_real_cop_billion"],
            "private_consumption_real_cop_billion": result["private_consumption_real_cop_billion"],
            "investment_real_cop_billion": result["investment_real_cop_billion"],
            "government_consumption_real_cop_billion": result["government_consumption_real_cop_billion"],
            "exports_real_cop_billion": result["exports_real_cop_billion"],
            "imports_real_cop_billion": result["imports_real_cop_billion"],
            "net_exports_real_cop_billion": result["net_exports_real_cop_billion"],
            "trm_cop_per_usd": result["trm_cop_per_usd"],
            "real_exchange_rate_index": result["real_exchange_rate_index"],
            "policy_rate_pct": result["policy_rate_pct"],
            "current_account_usd_m": result["current_account_usd_m"],
            "financial_account_inflow_usd_m": result["financial_account_inflow_usd_m"],
            "output_gap_pct": result["output_gap_pct"],
        })
    return pd.DataFrame(rows)


def project_scenario(
    calibration: Mapping[str, float],
    scenario_name: str,
    parameters: Mapping[str, float] | None = None,
    mobility: str = "perfecta",
    base_year: int | None = None,
) -> pd.DataFrame:
    """Atajo: proyecta uno de los escenarios pre-definidos por nombre."""
    if scenario_name not in PROJECTION_SCENARIOS:
        raise KeyError(f"Escenario {scenario_name!r} no esta en PROJECTION_SCENARIOS.")
    scenario = PROJECTION_SCENARIOS[scenario_name]
    return project(calibration, scenario.annual_shocks, parameters, mobility, base_year)
