"""Construye la tabla consolidada de cuentas nacionales + proyecciones.

Combina datos historicos del DANE (quarterly_master.csv, agregados a anual)
con la proyeccion deterministica del modelo (mf_projection.project).

Estructura:
- Filas = variables agrupadas en 4 bloques (cuentas nacionales en niveles,
  tasas de crecimiento, sector externo, sector monetario).
- Columnas = anios: ``HISTORY_YEARS`` historicos + 1 estimado + 5 proyectados.
- Las celdas se entregan como floats; el formateo es responsabilidad de la UI.

Convencion de unidades:
- Cuentas nacionales: COP miles de millones a precios constantes de 2015,
  agregadas anualmente (suma de 4 trimestres).
- TRM: COP/USD, promedio anual.
- Tasas: porcentaje, fin de anio para tasas de politica; promedio anual para
  inflacion observada.
- Cuenta corriente: USD millones, agregado anual (suma de 4 trimestres).

Convencion de etiquetas: ``YYYY`` historico observado, ``YYYYe`` estimado del
anio en curso (calibracion base), ``YYYYp`` proyectado por el modelo.
"""

from __future__ import annotations

from typing import Mapping

import pandas as pd


HISTORY_YEARS = 5
QUARTERS_PER_YEAR = 4


FLOW_VARIABLES_QUARTERLY = (
    "gdp_real_cop_billion",
    "private_consumption_real_cop_billion",
    "government_consumption_real_cop_billion",
    "investment_real_cop_billion",
    "exports_real_cop_billion",
    "imports_real_cop_billion",
)

FLOW_VARIABLES_USD = ("current_account_usd_m",)

STOCK_VARIABLES = (
    "trm_cop_per_usd",
    "real_exchange_rate_index",
    "policy_rate_pct",
)


def _annualize_historical(quarterly_df: pd.DataFrame, year: int) -> dict[str, float | None]:
    """Suma flujos trimestrales y promedia variables stock para un anio.

    Solo anualiza si el anio esta COMPLETO (4 trimestres). Un anio parcial (p.ej.
    cuando el DANE acaba de publicar 2026Q1) NO se suma como anual: sumar 1-3
    trimestres subregistraria el PIB ~4x y contaminaria el anclaje de las
    proyecciones. En ese caso devuelve {} y el anio se trata como no observado.
    """
    sub = quarterly_df[quarterly_df["year"] == year]
    if sub.empty or sub["quarter"].nunique() < QUARTERS_PER_YEAR:
        return {}
    out: dict[str, float | None] = {}
    for col in FLOW_VARIABLES_QUARTERLY:
        if col in sub.columns and sub[col].notna().all():
            out[col] = float(sub[col].sum())
    out["net_exports_real_cop_billion"] = (
        out.get("exports_real_cop_billion", 0.0) - out.get("imports_real_cop_billion", 0.0)
        if "exports_real_cop_billion" in out and "imports_real_cop_billion" in out
        else None
    )
    if "trm_avg_cop_per_usd" in sub.columns and sub["trm_avg_cop_per_usd"].notna().any():
        out["trm_cop_per_usd"] = float(sub["trm_avg_cop_per_usd"].dropna().mean())
    return out


def _annualize_projection(
    row: pd.Series,
    base_quarterly: Mapping[str, float] | None = None,
    anchor_annual: Mapping[str, float] | None = None,
) -> dict[str, float]:
    """Convierte una fila de proyeccion (trimestral) a equivalente anual.

    Si se pasa ``base_quarterly`` (los valores trimestrales del calibrado base
    que produce el modelo) y ``anchor_annual`` (los valores anuales observados
    del ultimo anio), aplica el % de cambio del modelo al ancla observada.
    Esto evita la discontinuidad cuando el calibrado se hace sobre Q4 (que
    suele tener estacionalidad fuerte en G).
    Si no se pasa ancla, multiplica por 4 (aproximacion mas burda).
    """
    out: dict[str, float] = {}
    flow_cols = FLOW_VARIABLES_QUARTERLY + ("net_exports_real_cop_billion",)
    for col in flow_cols:
        if col not in row.index:
            continue
        proj_q = float(row[col])
        if base_quarterly and anchor_annual and col in base_quarterly and col in anchor_annual:
            base_q = float(base_quarterly[col])
            if abs(base_q) > 1e-9:
                pct_change = proj_q / base_q - 1.0
                out[col] = float(anchor_annual[col]) * (1.0 + pct_change)
                continue
            if base_q == 0 and proj_q == 0:
                out[col] = float(anchor_annual[col])
                continue
        out[col] = proj_q * QUARTERS_PER_YEAR
    for col in FLOW_VARIABLES_USD:
        if col in row.index:
            out[col] = float(row[col]) * QUARTERS_PER_YEAR
    for col in STOCK_VARIABLES:
        if col in row.index:
            out[col] = float(row[col])
    out["output_gap_pct"] = float(row.get("output_gap_pct", 0.0))
    return out


def _annualize_calibration(calibration: Mapping[str, float]) -> dict[str, float]:
    """Valores de stock o flujo trimestral del snapshot, para el ultimo anio.

    No multiplica flujos x4: si el snapshot es Q4 y queremos un proxy de "valor
    representativo" para el anio, mejor consumir quarterly_master con los 4
    trimestres reales en _annualize_historical.
    """
    out: dict[str, float] = {}
    out["trm_cop_per_usd"] = float(calibration.get("trm_cop_per_usd", 0.0))
    out["real_exchange_rate_index"] = float(calibration.get("real_exchange_rate_index", 100.0))
    out["policy_rate_pct"] = float(calibration.get("policy_rate_pct", 0.0))
    if "current_account_usd_m" in calibration:
        out["current_account_usd_m"] = float(calibration["current_account_usd_m"]) * QUARTERS_PER_YEAR
    return out


VARIABLE_ROWS: list[tuple[str, str, str, str]] = [
    # (block, variable_label, source_key, unit)
    ("Cuentas nacionales (COP bn 2015)", "PIB real", "gdp_real_cop_billion", "COP bn"),
    ("Cuentas nacionales (COP bn 2015)", "Consumo privado (C)", "private_consumption_real_cop_billion", "COP bn"),
    ("Cuentas nacionales (COP bn 2015)", "Inversion (I)", "investment_real_cop_billion", "COP bn"),
    ("Cuentas nacionales (COP bn 2015)", "Gasto publico (G)", "government_consumption_real_cop_billion", "COP bn"),
    ("Cuentas nacionales (COP bn 2015)", "Exportaciones (X)", "exports_real_cop_billion", "COP bn"),
    ("Cuentas nacionales (COP bn 2015)", "Importaciones (M)", "imports_real_cop_billion", "COP bn"),
    ("Cuentas nacionales (COP bn 2015)", "Exportaciones netas (NX)", "net_exports_real_cop_billion", "COP bn"),
    ("Sector externo", "TRM promedio anual", "trm_cop_per_usd", "COP/USD"),
    ("Sector externo", "Tipo cambio real (indice)", "real_exchange_rate_index", "base 100"),
    ("Sector externo", "Cuenta corriente", "current_account_usd_m", "USD m anual"),
    ("Sector monetario", "Tasa de politica monetaria", "policy_rate_pct", "% e.a."),
    ("Sector monetario", "Brecha de producto", "output_gap_pct", "%"),
]


def build_consolidated_table(
    quarterly_df: pd.DataFrame,
    calibration: Mapping[str, float],
    projection_df: pd.DataFrame,
    last_observed_year: int,
    history_years: int = HISTORY_YEARS,
) -> pd.DataFrame:
    """Tabla anual: ``history_years`` anios observados + horizonte proyectado.

    ``last_observed_year`` es el ultimo anio totalmente observado en
    ``quarterly_df`` (e.g. 2025 si el snapshot llega a 2025Q4). Las columnas
    quedan como ``YYYY`` (observado) y ``YYYYp`` (proyectado).
    """
    quarterly_df = quarterly_df.copy()
    quarterly_df["year"] = quarterly_df["year"].astype(int)
    historical_years = list(range(last_observed_year - history_years + 1, last_observed_year + 1))
    historical_data = {y: _annualize_historical(quarterly_df, y) for y in historical_years}
    base_data = _annualize_calibration(calibration)

    base_quarterly_levels = {
        col: float(calibration[col])
        for col in FLOW_VARIABLES_QUARTERLY
        if col in calibration
    }
    base_quarterly_levels["net_exports_real_cop_billion"] = (
        base_quarterly_levels.get("exports_real_cop_billion", 0.0)
        - base_quarterly_levels.get("imports_real_cop_billion", 0.0)
    )
    anchor_annual_levels = historical_data[last_observed_year]

    projection_data = {
        int(row["year_offset"]): _annualize_projection(row, base_quarterly_levels, anchor_annual_levels)
        for _, row in projection_df.iterrows()
    }

    columns = [str(y) for y in historical_years] + [f"{last_observed_year + i}p" for i in range(1, len(projection_df) + 1)]

    def _resolve(key: str, year: int) -> float | None:
        value = historical_data[year].get(key)
        if value is not None:
            return value
        if year == last_observed_year:
            return base_data.get(key)
        return None

    rows = []
    index_tuples = []
    for block, label, key, unit in VARIABLE_ROWS:
        index_tuples.append((block, f"{label} ({unit})"))
        row_values = [_resolve(key, y) for y in historical_years]
        for offset in range(1, len(projection_df) + 1):
            row_values.append(projection_data[offset].get(key))
        rows.append(row_values)

    growth_block = "Crecimiento real anual (%)"
    for block, label, key, unit in VARIABLE_ROWS:
        if block != "Cuentas nacionales (COP bn 2015)":
            continue
        index_tuples.append((growth_block, f"{label} (%)"))
        levels = [_resolve(key, y) for y in historical_years]
        for offset in range(1, len(projection_df) + 1):
            levels.append(projection_data[offset].get(key))
        growth_values = [None]
        for i in range(1, len(levels)):
            prev, cur = levels[i - 1], levels[i]
            if prev is None or cur is None or prev == 0:
                growth_values.append(None)
            else:
                growth_values.append((cur / prev - 1.0) * 100.0)
        rows.append(growth_values)

    table = pd.DataFrame(rows, columns=columns, index=pd.MultiIndex.from_tuples(index_tuples, names=["bloque", "variable"]))
    return table


def to_csv_bytes(table: pd.DataFrame) -> bytes:
    """Serializa la tabla a CSV UTF-8 con BOM (compatible con Excel en espanol)."""
    return table.to_csv(index=True, encoding="utf-8-sig").encode("utf-8-sig")
