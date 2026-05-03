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
    """Repite el mismo choque cada anio del horizonte (sin cumulacion)."""
    return [Shock(**{f: getattr(shock, f) for f in Shock.__dataclass_fields__}) for _ in range(HORIZON_YEARS)]


def _recurring_path(annual_shock: Shock) -> list[Shock]:
    """Choque recurrente lineal: el ano N aplica N veces el choque anual.

    Asi un escenario de "expansion fiscal +5% G recurrente" significa que cada
    ano G crece 5 puntos adicionales sobre el ano anterior. En el ano 5 el
    choque acumulado es +25% de G respecto al base. Este es el modo por defecto
    para que los 5 anos no salgan planos cuando el modelo es estatico.
    """
    paths = []
    for year_n in range(1, HORIZON_YEARS + 1):
        cumulated = Shock(**{
            field: getattr(annual_shock, field) * year_n
            for field in Shock.__dataclass_fields__
        })
        paths.append(cumulated)
    return paths


PROJECTION_SCENARIOS: dict[str, ProjectionScenario] = {
    "Base (sin choques)": ProjectionScenario(
        name="Base (sin choques)",
        description="Las exogenas se mantienen en su valor del calibrado base. Sirve como referencia: "
                    "los 5 anios coinciden con el equilibrio inicial.",
        annual_shocks=_const_path(Shock()),
    ),
    "Expansion fiscal recurrente (+5% G/anio)": ProjectionScenario(
        name="Expansion fiscal recurrente (+5% G/anio)",
        description="Gasto publico crece 5 puntos cada anio: +5% en ano 1, +10% en ano 2, "
                    "+25% en ano 5. Acumulacion lineal.",
        annual_shocks=_recurring_path(Shock(government_spending_pct=5.0)),
    ),
    "Subida tasa Fed recurrente (+50 bps/anio)": ProjectionScenario(
        name="Subida tasa Fed recurrente (+50 bps/anio)",
        description="Fed sube 50 pbs cada anio: +50 en ano 1, +100 en ano 2, +250 en ano 5. "
                    "Stress de financiamiento externo creciente.",
        annual_shocks=_recurring_path(Shock(foreign_rate_bp=50.0)),
    ),
    "Ciclo petrolero adverso recurrente (-5% Brent/anio)": ProjectionScenario(
        name="Ciclo petrolero adverso recurrente (-5% Brent/anio)",
        description="Precio Brent cae 5% cada anio: -5% en ano 1, -25% acumulado en ano 5. "
                    "Deterioro sostenido de terminos de intercambio.",
        annual_shocks=_recurring_path(Shock(oil_price_pct=-5.0)),
    ),
    "Subida prima de riesgo recurrente (+50 bps/anio)": ProjectionScenario(
        name="Subida prima de riesgo recurrente (+50 bps/anio)",
        description="Prima de riesgo Colombia sube 50 pbs cada anio: +50 en ano 1, +250 en ano 5. "
                    "Riesgo soberano creciente.",
        annual_shocks=_recurring_path(Shock(risk_premium_bp=50.0)),
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
