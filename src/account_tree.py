"""Arbol de descomposicion de la contabilidad nacional (nodo-enlace en SVG).

Genera un arbol limpio raiz -> ramas (creditos/debitos) -> hojas como SVG puro,
para renderizar en la app con components.html (sin depender de Plotly). Cubre:

- PIB por el lado del gasto (Y = C + I + G + X - M), anios historicos del DANE
  (2005-2025) -> permite descomponer "hacia atras".
- Cuentas externas (balanza de pagos) y fiscales (GNC) del MFMP 2026 (2025-2037)
  -> descompone "hacia adelante". Las vistas se arman desde mfmp_official.

Todas las funciones son puras (devuelven dicts o strings), de modo que el layout
del arbol queda cubierto por tests sin levantar Streamlit.
"""

from __future__ import annotations

from typing import Mapping

import pandas as pd

QUARTERS_PER_YEAR = 4

# Paleta del arbol: creditos (verde), debitos (rojo), saldo/raiz (azul).
PALETTE = {
    "ingreso": {"leaf": "#DCFCE7", "branch": "#BBF7D0", "text": "#065F46", "sub": "#047857"},
    "egreso": {"leaf": "#FEE2E2", "branch": "#FECACA", "text": "#991B1B", "sub": "#B91C1C"},
    "root": {"fill": "#DBEAFE", "text": "#1E3A8A", "sub": "#1D4ED8"},
}


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _node(label: str, value_label: str, kind: str) -> dict:
    return {"label": label, "value_label": value_label, "kind": kind}


# --------------------------------------------------------------------------- #
# Constructores de vistas (root + branches) desde los datos
# --------------------------------------------------------------------------- #

def expenditure_view(quarterly_df: pd.DataFrame, year: int) -> dict | None:
    """PIB por el lado del gasto para un anio (valores nominales, identidad exacta).

    Y = Consumo privado + Consumo publico + Inversion + Exportaciones - Importaciones.
    Devuelve None si el anio no tiene 4 trimestres completos en el panel.
    """
    sub = quarterly_df[quarterly_df["year"] == year]
    if sub["quarter"].nunique() < QUARTERS_PER_YEAR:
        return None
    c = float(sub["private_consumption_nominal_cop_billion"].sum())
    g = float(sub["government_consumption_nominal_cop_billion"].sum())
    inv = float(sub["investment_nominal_cop_billion"].sum())
    x = float(sub["exports_nominal_cop_billion"].sum())
    m = float(sub["imports_nominal_cop_billion"].sum())
    y = float(sub["gdp_nominal_cop_billion"].sum())

    def pct(v: float) -> float:
        return v / y * 100 if y else 0.0

    def bn(v: float) -> str:  # mil-millones -> billones (10^12)
        return f"${v/1000:,.0f} bn"

    leaves_pos = [
        _node("Consumo privado (C)", f"+{pct(c):.1f}% · {bn(c)}", "ingreso"),
        _node("Consumo publico (G)", f"+{pct(g):.1f}% · {bn(g)}", "ingreso"),
        _node("Inversion (FBK, I)", f"+{pct(inv):.1f}% · {bn(inv)}", "ingreso"),
        _node("Exportaciones (X)", f"+{pct(x):.1f}% · {bn(x)}", "ingreso"),
    ]
    leaves_neg = [_node("Importaciones (M)", f"-{pct(m):.1f}% · -{bn(m)}", "egreso")]
    return {
        "root": {"label": "PIB (lado del gasto)",
                 "sublines": [bn(y) + " corrientes", str(year)]},
        "branches": [
            {"label": "Demanda (+)", "value_label": f"+{pct(c+g+inv+x):.1f}% PIB",
             "kind": "ingreso", "leaves": leaves_pos},
            {"label": "(-) Importaciones", "value_label": f"-{pct(m):.1f}% PIB",
             "kind": "egreso", "leaves": leaves_neg},
        ],
        "identity": (f"PIB = C + G + I + X - M = "
                     f"{pct(c):.1f} + {pct(g):.1f} + {pct(inv):.1f} + {pct(x):.1f} - {pct(m):.1f} "
                     f"= 100% del PIB ({bn(y)} corrientes)."),
    }


def _mfmp_branch_view(leaves: list[dict], root_label: str, root_sublines: list[str],
                      credit_label: str, debit_label: str) -> dict:
    """Arma una vista (root+branches) a partir de hojas con kind y value_pct/cop/usd."""
    def fmt(n: dict) -> str:
        return f"{n['value_pct']:+.1f}% · ${n['value_cop_billion']:,.0f} bn"

    cred = [n for n in leaves if n["kind"] == "ingreso" and abs(n["value_pct"]) >= 0.05]
    deb = [n for n in leaves if n["kind"] == "egreso" and abs(n["value_pct"]) >= 0.05]
    branches = []
    if cred:
        branches.append({
            "label": credit_label,
            "value_label": f"+{sum(n['value_pct'] for n in cred):.1f}% PIB",
            "kind": "ingreso",
            "leaves": [_node(n["label"].strip(), fmt(n), "ingreso") for n in cred],
        })
    if deb:
        branches.append({
            "label": debit_label,
            "value_label": f"{sum(n['value_pct'] for n in deb):.1f}% PIB",
            "kind": "egreso",
            "leaves": [_node(n["label"].strip(), fmt(n), "egreso") for n in deb],
        })
    return {"root": {"label": root_label, "sublines": root_sublines}, "branches": branches}


def external_view(tree: Mapping) -> dict:
    cc = next(n for n in tree["external"] if n["label"] == "Cuenta corriente")
    return _mfmp_branch_view(
        tree["external_leaves"],
        "Cuenta corriente",
        [f"{cc['value_pct']:+.1f}% PIB", f"{cc['value_usd_m']:,.0f} USD m"],
        "Ingresos (creditos)", "Egresos (debitos)",
    )


def fiscal_view(tree: Mapping) -> dict:
    bal = next(n for n in tree["fiscal"] if n["label"] == "Balance fiscal total (GNC)")
    return _mfmp_branch_view(
        tree["fiscal_leaves"],
        "Balance fiscal GNC",
        [f"{bal['value_pct']:+.1f}% PIB", f"Primario {tree['primary_balance_pct_gdp']:+.1f}%"],
        "Ingreso total", "Gasto total",
    )


# --------------------------------------------------------------------------- #
# Render SVG (nodo-enlace)
# --------------------------------------------------------------------------- #

def tree_svg(title: str, view: dict, width: int = 680) -> str:
    """Renderiza una vista (root + branches con leaves) como arbol nodo-enlace SVG."""
    root = view["root"]
    branches = view["branches"]
    leaves_flat = [(bi, lf) for bi, b in enumerate(branches) for lf in b["leaves"]]
    n = max(1, len(leaves_flat))

    leaf_h, step = 30, 38
    top = 30 if title else 12
    def cy(i: int) -> int:  # centro vertical de la hoja i
        return top + leaf_h // 2 + i * step
    height = cy(n - 1) + leaf_h // 2 + 14

    rootx, rootw = 12, 150
    brx, brw = 192, 152
    lfx = 362
    lfw = width - lfx - 12

    parts = [
        f'<svg width="100%" viewBox="0 0 {width} {height}" '
        f'style="max-width:{width}px;height:auto;display:block" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="Inter, Segoe UI, Arial, sans-serif">'
    ]
    if title:
        parts.append(f'<text x="12" y="20" font-size="15" font-weight="500" fill="#172033">{_esc(title)}</text>')

    # indices globales por rama
    bounds = []  # (i0, i1) por rama
    gi = 0
    for b in branches:
        k = len(b["leaves"])
        bounds.append((gi, gi + k - 1))
        gi += k

    root_top = cy(0) - leaf_h // 2
    root_bot = cy(n - 1) + leaf_h // 2
    root_cy = (root_top + root_bot) // 2

    # conectores raiz -> rama
    for (i0, i1), b in zip(bounds, branches):
        bc = (cy(i0) - leaf_h // 2 + cy(i1) + leaf_h // 2) // 2
        parts.append(
            f'<path d="M{rootx+rootw},{root_cy} C{rootx+rootw+16},{root_cy} '
            f'{brx-16},{bc} {brx},{bc}" fill="none" stroke="#94A3B8" stroke-width="1.2"/>'
        )
    # conectores rama -> hoja
    for (i0, i1), b in zip(bounds, branches):
        bc = (cy(i0) - leaf_h // 2 + cy(i1) + leaf_h // 2) // 2
        for i in range(i0, i1 + 1):
            parts.append(
                f'<path d="M{brx+brw},{bc} C{brx+brw+16},{bc} '
                f'{lfx-16},{cy(i)} {lfx},{cy(i)}" fill="none" stroke="#94A3B8" stroke-width="1.2"/>'
            )

    # raiz
    rc = PALETTE["root"]
    parts.append(f'<rect x="{rootx}" y="{root_top}" width="{rootw}" height="{root_bot-root_top}" '
                 f'rx="8" fill="{rc["fill"]}"/>')
    rcx = rootx + rootw // 2
    parts.append(f'<text x="{rcx}" y="{root_cy-4}" text-anchor="middle" font-size="13" '
                 f'font-weight="500" fill="{rc["text"]}">{_esc(root["label"])}</text>')
    for j, sl in enumerate(root.get("sublines", [])):
        parts.append(f'<text x="{rcx}" y="{root_cy+13+j*16}" text-anchor="middle" font-size="11" '
                     f'fill="{rc["sub"]}">{_esc(sl)}</text>')

    # ramas + hojas
    for (i0, i1), b in zip(bounds, branches):
        pal = PALETTE[b["kind"]]
        b_top = cy(i0) - leaf_h // 2
        b_bot = cy(i1) + leaf_h // 2
        bc = (b_top + b_bot) // 2
        parts.append(f'<rect x="{brx}" y="{b_top}" width="{brw}" height="{b_bot-b_top}" '
                     f'rx="7" fill="{pal["branch"]}"/>')
        bcx = brx + brw // 2
        parts.append(f'<text x="{bcx}" y="{bc-3}" text-anchor="middle" font-size="13" '
                     f'font-weight="500" fill="{pal["text"]}">{_esc(b["label"])}</text>')
        parts.append(f'<text x="{bcx}" y="{bc+14}" text-anchor="middle" font-size="11" '
                     f'fill="{pal["sub"]}">{_esc(b["value_label"])}</text>')
        for i, lf in zip(range(i0, i1 + 1), b["leaves"]):
            ly = cy(i) - leaf_h // 2
            parts.append(f'<rect x="{lfx}" y="{ly}" width="{lfw}" height="{leaf_h}" '
                         f'rx="6" fill="{pal["leaf"]}"/>')
            parts.append(f'<text x="{lfx+12}" y="{cy(i)+4}" font-size="13" font-weight="500" '
                         f'fill="{pal["text"]}">{_esc(lf["label"])}</text>')
            parts.append(f'<text x="{lfx+lfw-12}" y="{cy(i)+4}" text-anchor="end" font-size="11" '
                         f'fill="{pal["sub"]}">{_esc(lf["value_label"])}</text>')

    parts.append("</svg>")
    return "".join(parts)


def svg_height(view: dict, title: bool = True) -> int:
    """Altura en px del SVG para dimensionar components.html."""
    n = max(1, sum(len(b["leaves"]) for b in view["branches"]))
    top = 30 if title else 12
    return top + 15 + (n - 1) * 38 + 15 + 14
