"""Arbol de descomposicion de la contabilidad nacional (treemap jerarquico).

Construye jerarquias anidadas (raiz -> grupos -> componentes) que se renderizan
como treemap de Plotly en la app: el usuario hace clic en una rama para
descomponerla mas (drill-down nativo) y vuelve por la barra de ruta. Cubre:

- PIB por el lado del gasto (Y = C + I + G + X - M), anios historicos del DANE
  (2005-2025) -> descompone "hacia atras".
- Cuentas externas (balanza de pagos) y fiscales (GNC) del MFMP 2026 (2025-2037)
  -> descompone "hacia adelante".

El tamano de cada celda es la MAGNITUD absoluta (% del PIB); el color codifica el
signo (verde = entra/credito/ingreso, rojo = sale/debito/egreso). El saldo neto y
los montos en COP/USD se muestran en la etiqueta y el hover.

Funciones puras (devuelven dicts/arrays), cubiertas por tests sin levantar Streamlit.
"""

from __future__ import annotations

from typing import Mapping

import pandas as pd

QUARTERS_PER_YEAR = 4

# Colores: hoja vs grupo, por signo; raiz neutra.
_C_POS_LEAF, _C_POS_GRP = "#16a34a", "#86efac"
_C_NEG_LEAF, _C_NEG_GRP = "#dc2626", "#fca5a5"
_C_ROOT = "#334155"


def _leaf(label: str, pct: float, cop: float | None = None, usd: float | None = None) -> dict:
    return {"label": label, "net_pct": float(pct), "cop": cop, "usd": usd, "children": []}


def _group(label: str, children: list[dict], net_override: float | None = None,
           cop: float | None = None) -> dict:
    return {"label": label, "children": children, "net_override": net_override, "cop": cop}


# --------------------------------------------------------------------------- #
# Constructores de jerarquia
# --------------------------------------------------------------------------- #

def expenditure_hierarchy(quarterly_df: pd.DataFrame, year: int) -> dict | None:
    """PIB por el lado del gasto (nominal, identidad exacta). None si anio parcial."""
    sub = quarterly_df[quarterly_df["year"] == year]
    if sub["quarter"].nunique() < QUARTERS_PER_YEAR:
        return None
    y = float(sub["gdp_nominal_cop_billion"].sum())

    def comp(col: str) -> tuple[float, float]:
        v = float(sub[col].sum())
        return v / y * 100.0, v / 1000.0  # (% PIB, billones 10^12)

    c_pct, c_cop = comp("private_consumption_nominal_cop_billion")
    g_pct, g_cop = comp("government_consumption_nominal_cop_billion")
    i_pct, i_cop = comp("investment_nominal_cop_billion")
    x_pct, x_cop = comp("exports_nominal_cop_billion")
    m_pct, m_cop = comp("imports_nominal_cop_billion")

    consumo = _group("Consumo", [
        _leaf("Consumo privado (C)", c_pct, c_cop),
        _leaf("Consumo publico (G)", g_pct, g_cop),
    ])
    root = _group(f"PIB por el gasto · {year}", [
        consumo,
        _leaf("Inversion (FBK)", i_pct, i_cop),
        _leaf("Exportaciones (X)", x_pct, x_cop),
        _leaf("Importaciones (M)", -m_pct, -m_cop),
    ], net_override=100.0, cop=y / 1000.0)
    return root


def _ext_index(tree: Mapping) -> dict:
    return {n["label"].strip(): n for n in tree["external"]}


def external_hierarchy(tree: Mapping) -> dict:
    """Balanza de pagos: cuenta corriente -> balanza comercial -> exportaciones..."""
    E = _ext_index(tree)

    def L(key: str, label: str) -> dict:
        n = E[key]
        return _leaf(label, n["value_pct"], n["value_cop_billion"], n["value_usd_m"])

    exports = _group("Exportaciones de bienes", [
        L("Tradicionales (minero-energ.)", "Tradicionales"),
        L("No tradicionales", "No tradicionales"),
    ])
    balanza = _group("Balanza comercial", [exports, L("Importaciones de bienes", "Importaciones")])
    children = [balanza]
    serv = E["Servicios (neto)"]
    if abs(serv["value_pct"]) >= 0.05:
        children.append(L("Servicios (neto)", "Servicios"))
    children.append(L("Renta factorial (ingreso primario)", "Renta factorial"))
    children.append(L("Transferencias (ingreso secundario)", "Transferencias"))

    cc = E["Cuenta corriente"]
    return _group(f"Cuenta corriente · {tree['year']}", children,
                  net_override=cc["value_pct"], cop=cc["value_cop_billion"])


def fiscal_hierarchy(tree: Mapping) -> dict:
    """Sector fiscal del GNC: balance -> ingreso/gasto -> componentes."""
    F = {n["label"].strip(): n for n in tree["fiscal"]}

    def L(key: str, label: str) -> dict:
        n = F[key]
        return _leaf(label, n["value_pct"], n["value_cop_billion"], n["value_usd_m"])

    ingreso_children = [L("Tributarios", "Tributarios"),
                        L("Recursos de capital", "Recursos de capital"),
                        L("Fondos especiales", "Fondos especiales")]
    aj = F["Ajuste requerido en ingreso"]
    if abs(aj["value_pct"]) >= 0.05:
        ingreso_children.append(L("Ajuste requerido en ingreso", "Ajuste requerido"))
    ingreso = _group("Ingreso total", ingreso_children)
    gasto = _group("Gasto total", [L("Gasto primario", "Gasto primario"),
                                   L("Intereses", "Intereses")])
    bal = F["Balance fiscal total (GNC)"]
    return _group(f"Balance fiscal GNC · {tree['year']}", [ingreso, gasto],
                  net_override=bal["value_pct"], cop=bal["value_cop_billion"])


# --------------------------------------------------------------------------- #
# Aplanado a arrays de treemap (Plotly)
# --------------------------------------------------------------------------- #

def _size_of(n: dict) -> float:
    if n["children"]:
        return sum(_size_of(c) for c in n["children"])
    return abs(n["net_pct"])


def _net_of(n: dict) -> float:
    if n.get("net_override") is not None:
        return n["net_override"]
    if n["children"]:
        return sum(_net_of(c) for c in n["children"])
    return n["net_pct"]


def treemap_arrays(root: dict) -> dict:
    """Aplana la jerarquia a listas paralelas para go.Treemap (branchvalues='total').

    El valor (tamano) de cada nodo es la suma de magnitudes de sus hojas, de modo
    que padre == suma de hijos y el treemap dibuja todos los niveles.
    """
    ids: list[str] = []
    labels: list[str] = []
    parents: list[str] = []
    values: list[float] = []
    colors: list[str] = []
    text: list[str] = []
    hover: list[str] = []

    def amount(n: dict, net: float) -> str:
        cop = n.get("cop")
        if cop is None and not n["children"]:
            cop = n.get("cop")
        if cop is not None:
            s = f"{net:+.1f}% del PIB · ${cop:,.0f} bn COP"
            if n.get("usd") is not None:
                s += f" · {n['usd']:,.0f} USD m"
            return s
        return f"{net:+.1f}% del PIB"

    def rec(n: dict, parent_id: str) -> None:
        nid = f"{parent_id}|{n['label']}" if parent_id else n["label"]
        net = _net_of(n)
        is_root = parent_id == ""
        is_group = bool(n["children"])
        ids.append(nid)
        labels.append(n["label"])
        parents.append(parent_id)
        values.append(round(_size_of(n), 4))
        if is_root:
            colors.append(_C_ROOT)
        elif net >= 0:
            colors.append(_C_POS_GRP if is_group else _C_POS_LEAF)
        else:
            colors.append(_C_NEG_GRP if is_group else _C_NEG_LEAF)
        text.append(f"{net:+.1f}% PIB")
        hover.append(amount(n, net))
        for c in n["children"]:
            rec(c, nid)

    rec(root, "")
    return {"ids": ids, "labels": labels, "parents": parents, "values": values,
            "colors": colors, "text": text, "hover": hover}
