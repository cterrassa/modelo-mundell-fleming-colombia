"""Cifras oficiales del Marco Fiscal de Mediano Plazo (MFMP) 2026 del MHCP.

Fuente unica de verdad para la senda oficial de mediano plazo publicada por el
Ministerio de Hacienda y Credito Publico (Direccion General de Politica
Macroeconomica, DGPM). Los valores estan transcritos textualmente del documento
MFMP 2026:

- Tabla 3.1  "Principales variables macroeconomicas y fiscales" (2025-2037)
- Tabla 3.2  "Balance fiscal del GNC 2024-2037 (% del PIB)"  (desagregacion)
- Grafico 3.4 "Proyecciones de balance de cuenta corriente" (% del PIB, 2025-2037)
- Tabla 1.3  "Balance fiscal 2024-2026 ($mm y % del PIB)"  (ancla de PIB nominal)

A diferencia del resto de la app (que resuelve el modelo Mundell-Fleming), este
modulo NO simula: expone las proyecciones del propio MHCP. Sirve para (a) la
senda oficial de cuentas nacionales y TRM del quinquenio y (b) el arbol de
descomposicion de la contabilidad nacional por anio.

El PIB nominal en billones (10^12 COP) se DERIVA: se ancla en 2026 con la Tabla
1.3 (~2.016 billones) y se encadena con el crecimiento nominal de la Tabla 3.1.
Las conversiones a COP/USD son ilustrativas; las cifras autoritativas son los
% del PIB.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

_CSV_PATH = Path(__file__).resolve().parents[1] / "data_processed" / "mfmp_2026_oficial.csv"

# Anios cubiertos por TODAS las tablas (Tabla 3.1 y Grafico 3.4 arrancan en 2025).
YEARS: tuple[int, ...] = tuple(range(2025, 2038))  # 2025..2037

# PIB nominal 2026 (billones COP, 10^12). Ancla = promedio de los 3 despejes de la
# Tabla 1.3: ingreso 325.281/0,161; gasto 431.760/0,214; balance -106.479/-0,053.
_NOMINAL_GDP_2026 = 2016.0

# --- Series oficiales (un valor por anio 2025..2037, 13 valores) ---------------
# Tabla 3.1
_MACRO = {
    "pib_real_growth_pct":        [2.6, 2.6, 2.2, 2.8, 2.8, 2.8, 2.9, 3.0, 3.0, 3.0, 3.0, 2.9, 2.9],
    "pib_nominal_growth_pct":     [8.1, 9.0, 5.8, 5.9, 5.9, 5.9, 6.0, 6.1, 6.1, 6.1, 6.1, 6.0, 5.9],
    "trading_partners_growth_pct":[2.6, 2.6, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5],
    "current_account_pct_gdp":    [-2.4, -2.2, -2.0, -2.1, -2.2, -2.4, -2.7, -2.9, -3.0, -3.0, -2.8, -2.6, -2.4],
    "trm_average":                [4053, 3757, 3859, 3941, 4026, 4112, 4200, 4290, 4382, 4475, 4571, 4669, 4769],
    "depreciation_pct":           [-0.5, -7.3, 2.7, 2.1, 2.1, 2.1, 2.1, 2.1, 2.1, 2.1, 2.1, 2.1, 2.1],
    "brent_usd":                  [68.2, 85.5, 74.9, 76.4, 77.9, 79.5, 81.1, 82.7, 84.4, 86.1, 87.8, 89.5, 91.3],
    "oil_production_kbpd":        [746.5, 730.6, 716.8, 710.0, 703.3, 696.7, 690.1, 683.6, 677.2, 670.9, 664.6, 658.3, 652.2],
    "inflation_eop_pct":          [5.1, 6.0, 4.4, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0],
    "local_rate_pct":             [6.8, 7.4, 9.3, 8.2, 8.4, 8.1, 8.1, 8.3, 8.4, 8.3, 8.2, 7.9, 7.8],
    "foreign_rate_pct":           [5.0, 3.3, 4.0, 4.3, 4.4, 4.4, 4.5, 4.7, 4.7, 4.7, 4.7, 4.8, 4.9],
    "gnc_net_debt_pct_gdp":       [58.6, 58.9, 58.9, 59.3, 59.6, 59.4, 59.1, 58.8, 58.5, 58.3, 58.0, 57.6, 57.3],
    "gg_fiscal_balance_pct_gdp":  [-6.1, -5.1, -3.8, -3.1, -3.1, -2.6, -2.4, -2.4, -2.4, -2.5, -2.3, -2.2, -2.2],
    "gg_consolidated_debt_pct_gdp":[59.2, 56.1, 55.8, 55.8, 56.0, 55.6, 55.1, 54.5, 54.1, 53.6, 53.0, 52.4, 51.8],
}

# Tabla 3.2 (balance fiscal del GNC, % del PIB). Desagregacion de ingresos y gastos.
_FISCAL = {
    "gnc_revenue_pct_gdp":        [16.3, 16.1, 17.3, 17.8, 17.9, 18.0, 18.2, 18.3, 18.3, 18.3, 18.4, 18.4, 18.4],
    "gnc_tax_revenue_pct_gdp":    [14.7, 14.6, 14.5, 14.6, 14.7, 14.8, 14.9, 15.0, 15.0, 15.1, 15.1, 15.2, 15.2],
    "gnc_nontax_revenue_pct_gdp": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "gnc_special_funds_pct_gdp":  [0.3, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2],
    "gnc_capital_revenue_pct_gdp":[1.3, 1.3, 1.2, 1.3, 1.4, 1.4, 1.4, 1.4, 1.4, 1.4, 1.4, 1.4, 1.4],
    "gnc_required_adjustment_pct_gdp":[0.0, 0.0, 1.4, 1.6, 1.6, 1.6, 1.6, 1.6, 1.6, 1.6, 1.6, 1.6, 1.6],
    "gnc_expense_pct_gdp":        [22.7, 21.4, 21.8, 21.4, 21.5, 21.2, 21.2, 21.3, 21.3, 21.3, 21.3, 21.2, 21.1],
    "gnc_interest_pct_gdp":       [2.8, 3.2, 3.9, 4.1, 4.2, 4.1, 4.1, 4.2, 4.2, 4.2, 4.1, 4.0, 3.9],
    "gnc_primary_expense_pct_gdp":[19.9, 18.1, 17.8, 17.3, 17.3, 17.0, 17.1, 17.1, 17.1, 17.2, 17.2, 17.3, 17.2],
    "gnc_fiscal_balance_pct_gdp": [-6.4, -5.3, -4.5, -3.6, -3.5, -3.1, -2.9, -3.0, -3.0, -3.0, -2.9, -2.8, -2.7],
    "gnc_primary_balance_pct_gdp":[-3.5, -2.1, -0.5, 0.5, 0.7, 1.0, 1.2, 1.2, 1.2, 1.1, 1.2, 1.2, 1.2],
}

# Grafico 3.4 (descomposicion de la cuenta corriente, % del PIB). Las exportaciones
# tradicionales y no tradicionales, importaciones, renta factorial y transferencias
# se leen del grafico; servicios se reconcilia para cerrar exactamente la identidad
# de cuenta corriente (en el MFMP es una linea neta pequena de ~0,1-0,2% del PIB).
_EXTERNAL = {
    "ca_traditional_exports_pct_gdp":   [7.0, 7.1, 6.6, 6.6, 6.5, 6.4, 6.4, 6.3, 6.3, 6.2, 6.2, 6.1, 6.1],
    "ca_nontraditional_exports_pct_gdp":[4.3, 3.8, 3.9, 4.0, 4.1, 4.2, 4.4, 4.5, 4.6, 4.7, 4.9, 5.0, 5.2],
    "ca_goods_imports_pct_gdp":         [-14.5, -13.4, -13.1, -13.2, -13.4, -13.6, -13.9, -14.2, -14.4, -14.6, -14.6, -14.6, -14.6],
    "ca_factor_income_pct_gdp":         [-2.7, -2.9, -2.8, -2.8, -2.8, -2.8, -2.8, -2.8, -2.7, -2.6, -2.6, -2.5, -2.4],
    "ca_transfers_pct_gdp":             [3.6, 3.2, 3.2, 3.2, 3.2, 3.2, 3.2, 3.2, 3.2, 3.2, 3.2, 3.2, 3.2],
}

# Cuota de la IED en el financiamiento del desbalance externo (MFMP, promedio
# 2028-2037). Se usa solo como nota cualitativa del arbol; no se desagrega por anio.
IED_SHARE_MEDIUM_TERM = 0.986


def _nominal_gdp_series() -> list[float]:
    """PIB nominal (billones COP) anclado en 2026 y encadenado con crecim. nominal."""
    g = _MACRO["pib_nominal_growth_pct"]
    idx_2026 = YEARS.index(2026)
    gdp = [0.0] * len(YEARS)
    gdp[idx_2026] = _NOMINAL_GDP_2026
    # hacia adelante: gdp[t] = gdp[t-1] * (1 + g[t]/100)
    for i in range(idx_2026 + 1, len(YEARS)):
        gdp[i] = gdp[i - 1] * (1 + g[i] / 100.0)
    # hacia atras: gdp[t-1] = gdp[t] / (1 + g[t]/100)
    for i in range(idx_2026 - 1, -1, -1):
        gdp[i] = gdp[i + 1] / (1 + g[i + 1] / 100.0)
    return [round(x, 1) for x in gdp]


def _services_reconciled() -> list[float]:
    """Servicios = saldo que cierra la identidad de cuenta corriente (1 decimal).

    CC = trad + no_trad + importaciones + renta + transferencias + servicios.
    """
    ca = _MACRO["current_account_pct_gdp"]
    out = []
    for i in range(len(YEARS)):
        others = (
            _EXTERNAL["ca_traditional_exports_pct_gdp"][i]
            + _EXTERNAL["ca_nontraditional_exports_pct_gdp"][i]
            + _EXTERNAL["ca_goods_imports_pct_gdp"][i]
            + _EXTERNAL["ca_factor_income_pct_gdp"][i]
            + _EXTERNAL["ca_transfers_pct_gdp"][i]
        )
        out.append(round(ca[i] - others, 1))
    return out


def build_dataframe() -> pd.DataFrame:
    """Construye el DataFrame oficial completo (una fila por anio 2025-2037)."""
    data: dict[str, list] = {"year": list(YEARS)}
    for block in (_MACRO, _FISCAL, _EXTERNAL):
        for k, v in block.items():
            if len(v) != len(YEARS):
                raise ValueError(f"Serie {k} tiene {len(v)} valores, se esperaban {len(YEARS)}.")
            data[k] = list(v)
    data["ca_services_pct_gdp"] = _services_reconciled()
    data["nominal_gdp_cop_billion"] = _nominal_gdp_series()
    df = pd.DataFrame(data)
    # Balanza comercial de bienes (derivada): exportaciones de bienes - importaciones.
    df["ca_goods_exports_pct_gdp"] = (
        df["ca_traditional_exports_pct_gdp"] + df["ca_nontraditional_exports_pct_gdp"]
    ).round(1)
    df["ca_trade_balance_pct_gdp"] = (
        df["ca_goods_exports_pct_gdp"] + df["ca_goods_imports_pct_gdp"]
    ).round(1)
    return df


def write_csv(path: Path = _CSV_PATH) -> Path:
    """Escribe data_processed/mfmp_2026_oficial.csv (reproducible)."""
    df = build_dataframe()
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")
    return path


def load(path: Path = _CSV_PATH) -> pd.DataFrame:
    """Lee el CSV oficial; si no existe, lo construye en memoria."""
    if path.exists():
        return pd.read_csv(path)
    return build_dataframe()


def _row(df: pd.DataFrame, year: int) -> pd.Series:
    sub = df[df["year"] == year]
    if sub.empty:
        raise ValueError(f"Anio {year} no esta en el MFMP 2026 (cobertura {min(YEARS)}-{max(YEARS)}).")
    return sub.iloc[0]


def projection_path(base_year: int | None = None, horizon: int = 5, df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Senda oficial para el quinquenio (o el horizonte pedido).

    base_year: ultimo anio observado. La proyeccion arranca en base_year+1. Si es
    None, arranca en el primer anio proyectado del MFMP (2026).
    """
    if df is None:
        df = load()
    if base_year is None:
        start = 2026
    else:
        start = base_year + 1
    end = start + horizon - 1
    out = df[(df["year"] >= start) & (df["year"] <= end)].copy()
    return out.reset_index(drop=True)


def _abs_values(pct: float, gdp_billion: float, trm: float) -> tuple[float, float]:
    """(% PIB) -> (billones COP, millones USD)."""
    cop_billion = pct / 100.0 * gdp_billion
    usd_m = cop_billion * 1e6 / trm  # billones COP = 10^12; /trm = USD; /1e6 = USD m
    return round(cop_billion, 1), round(usd_m, 0)


def national_accounts_tree(year: int, df: pd.DataFrame | None = None) -> dict:
    """Devuelve la descomposicion de la contabilidad nacional para un anio.

    Estructura lista para construir un arbol (icicle/treemap) y tablas de
    identidad. Dos ramas independientes: sector externo (balanza de pagos) y
    sector fiscal (GNC). Cada nodo trae value_pct (% PIB, con signo),
    value_cop_billion y value_usd_m.
    """
    if df is None:
        df = load()
    r = _row(df, year)
    gdp = float(r["nominal_gdp_cop_billion"])
    trm = float(r["trm_average"])

    def node(label: str, pct: float, parent: str, kind: str) -> dict:
        cop, usd = _abs_values(pct, gdp, trm)
        return {
            "label": label, "parent": parent, "kind": kind,
            "value_pct": round(float(pct), 2),
            "value_cop_billion": cop, "value_usd_m": usd,
        }

    ext = [
        node("Cuenta corriente", float(r["current_account_pct_gdp"]), "", "saldo"),
        node("Balanza comercial (bienes)", float(r["ca_trade_balance_pct_gdp"]), "Cuenta corriente", "saldo"),
        node("Exportaciones de bienes", float(r["ca_goods_exports_pct_gdp"]), "Balanza comercial (bienes)", "ingreso"),
        node("  Tradicionales (minero-energ.)", float(r["ca_traditional_exports_pct_gdp"]), "Exportaciones de bienes", "ingreso"),
        node("  No tradicionales", float(r["ca_nontraditional_exports_pct_gdp"]), "Exportaciones de bienes", "ingreso"),
        node("Importaciones de bienes", float(r["ca_goods_imports_pct_gdp"]), "Balanza comercial (bienes)", "egreso"),
        node("Servicios (neto)", float(r["ca_services_pct_gdp"]), "Cuenta corriente", "saldo"),
        node("Renta factorial (ingreso primario)", float(r["ca_factor_income_pct_gdp"]), "Cuenta corriente", "egreso"),
        node("Transferencias (ingreso secundario)", float(r["ca_transfers_pct_gdp"]), "Cuenta corriente", "ingreso"),
    ]

    fis = [
        node("Balance fiscal total (GNC)", float(r["gnc_fiscal_balance_pct_gdp"]), "", "saldo"),
        node("Ingreso total", float(r["gnc_revenue_pct_gdp"]), "Balance fiscal total (GNC)", "ingreso"),
        node("  Tributarios", float(r["gnc_tax_revenue_pct_gdp"]), "Ingreso total", "ingreso"),
        node("  Fondos especiales", float(r["gnc_special_funds_pct_gdp"]), "Ingreso total", "ingreso"),
        node("  Recursos de capital", float(r["gnc_capital_revenue_pct_gdp"]), "Ingreso total", "ingreso"),
        node("  Ajuste requerido en ingreso", float(r["gnc_required_adjustment_pct_gdp"]), "Ingreso total", "ingreso"),
        node("Gasto total", -float(r["gnc_expense_pct_gdp"]), "Balance fiscal total (GNC)", "egreso"),
        node("  Intereses", -float(r["gnc_interest_pct_gdp"]), "Gasto total", "egreso"),
        node("  Gasto primario", -float(r["gnc_primary_expense_pct_gdp"]), "Gasto total", "egreso"),
    ]

    # Hojas (gross flows) para el arbol icicle: creditos vs debitos. El signo se
    # codifica en 'kind'; el valor se grafica en magnitud absoluta. Distinto de
    # la lista jerarquica 'ext'/'fis' (que se usa para la tabla de identidad).
    serv = float(r["ca_services_pct_gdp"])
    external_leaves = [
        node("Export. tradicionales", float(r["ca_traditional_exports_pct_gdp"]), "", "ingreso"),
        node("Export. no tradicionales", float(r["ca_nontraditional_exports_pct_gdp"]), "", "ingreso"),
        node("Transferencias", float(r["ca_transfers_pct_gdp"]), "", "ingreso"),
        node("Servicios (neto)", serv, "", "ingreso" if serv >= 0 else "egreso"),
        node("Importaciones", float(r["ca_goods_imports_pct_gdp"]), "", "egreso"),
        node("Renta factorial", float(r["ca_factor_income_pct_gdp"]), "", "egreso"),
    ]
    fiscal_leaves = [
        node("Tributarios", float(r["gnc_tax_revenue_pct_gdp"]), "", "ingreso"),
        node("Recursos de capital", float(r["gnc_capital_revenue_pct_gdp"]), "", "ingreso"),
        node("Fondos especiales", float(r["gnc_special_funds_pct_gdp"]), "", "ingreso"),
        node("Ajuste requerido", float(r["gnc_required_adjustment_pct_gdp"]), "", "ingreso"),
        node("Intereses", -float(r["gnc_interest_pct_gdp"]), "", "egreso"),
        node("Gasto primario", -float(r["gnc_primary_expense_pct_gdp"]), "", "egreso"),
    ]

    return {
        "year": int(year),
        "nominal_gdp_cop_billion": gdp,
        "trm_average": trm,
        "external": ext,
        "fiscal": fis,
        "external_leaves": external_leaves,
        "fiscal_leaves": fiscal_leaves,
        "primary_balance_pct_gdp": float(r["gnc_primary_balance_pct_gdp"]),
        "net_debt_pct_gdp": float(r["gnc_net_debt_pct_gdp"]),
        "financial_account_pct_gdp": round(-float(r["current_account_pct_gdp"]), 2),
        "ied_share_medium_term": IED_SHARE_MEDIUM_TERM,
    }


# Paleta del arbol de cuentas: creditos (verde), debitos (rojo), agregados (gris/azul).
ACCOUNT_COLORS = {"ingreso": "#16a34a", "egreso": "#dc2626", "root": "#1f2937"}


def icicle_arrays(leaves: list[dict], root_label: str, value_field: str = "value_cop_billion") -> dict:
    """Arrays para un arbol icicle de creditos vs debitos (estructura pura, sin Plotly).

    Agrupa las hojas en dos ramas (Ingresos/creditos, Egresos/debitos) usando
    magnitudes absolutas. El valor de cada nodo padre se calcula como la SUMA de
    sus hijos, de modo que branchvalues='total' es consistente (padre >= hijos) y
    Plotly dibuja el arbol completo. Omite hojas con magnitud ~0.

    Devuelve dict con listas paralelas: ids, labels, parents, values, texts, colors.
    """
    leaves = [n for n in leaves if abs(float(n[value_field])) > 1e-9]
    branches = [
        ("Ingresos (creditos)", "ingreso", ACCOUNT_COLORS["ingreso"]),
        ("Egresos (debitos)", "egreso", ACCOUNT_COLORS["egreso"]),
    ]
    ids, labels, parents, values, texts, colors = [], [], [], [], [], []

    def branch_sum(kind: str) -> float:
        return sum(abs(float(n[value_field])) for n in leaves if n["kind"] == kind)

    root_total = sum(branch_sum(k) for _, k, _ in branches)
    ids.append(root_label); labels.append(root_label); parents.append("")
    values.append(root_total); texts.append(""); colors.append(ACCOUNT_COLORS["root"])
    for branch, kind, color in branches:
        sub = [n for n in leaves if n["kind"] == kind]
        if not sub:
            continue
        ids.append(branch); labels.append(branch); parents.append(root_label)
        values.append(branch_sum(kind)); texts.append(""); colors.append(color)
        for n in sub:
            lab = n["label"].strip()
            ids.append(f"{branch}/{lab}")
            labels.append(lab)
            parents.append(branch)
            values.append(abs(float(n[value_field])))
            texts.append(f"{n['value_pct']:+.1f}% PIB")
            colors.append(color)
    return {"ids": ids, "labels": labels, "parents": parents,
            "values": values, "texts": texts, "colors": colors}


if __name__ == "__main__":
    p = write_csv()
    print(f"Escrito {p}")
    print(build_dataframe().to_string(index=False))
