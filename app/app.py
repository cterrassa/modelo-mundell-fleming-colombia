from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from mf_model import MOBILITY_OPTIONS, SCENARIOS, SCENARIO_MECHANISMS, Shock, simulate  # noqa: E402
import mf_curves as curves  # noqa: E402
import live_data  # noqa: E402
from mf_projection import PROJECTION_SCENARIOS, project_scenario  # noqa: E402
from consolidated_table import build_consolidated_table, to_csv_bytes  # noqa: E402
import backtest as bt  # noqa: E402
from long_run import simulate_long_run  # noqa: E402
import equations as eqs  # noqa: E402


MOBILITY_LABELS = {
    "perfecta": "Flexible + movilidad perfecta",
    "imperfecta": "Flexible + movilidad imperfecta (Colombia)",
    "fijo": "Tipo de cambio fijo + movilidad perfecta",
}
MOBILITY_DESCRIPTIONS = {
    "perfecta": (
        "Caso canonico: tipo de cambio flexible y tasa local anclada por la paridad "
        "descubierta de intereses. La politica fiscal NO mueve Y (ΔY=0); el ajuste "
        "pasa por la TRM. La politica monetaria SI mueve Y."
    ),
    "imperfecta": (
        "Tipo de cambio flexible con movilidad finita: la tasa domestica es endogena "
        "y la politica fiscal SI mueve el producto. Calibracion empirica para Colombia."
    ),
    "fijo": (
        "El banco central defiende la paridad: TRM no se mueve, M se vuelve endogena. "
        "La politica fiscal SI mueve Y (no hay apreciacion que offset). La politica "
        "monetaria autonoma NO mueve Y (CB no controla M independientemente)."
    ),
}


st.set_page_config(page_title="Mundell-Fleming Colombia", layout="wide")


CSS = """
<style>
  .block-container { max-width: 1540px; padding-top: 1.2rem; padding-bottom: 3rem; }
  div[data-testid="stMetric"] { border: 1px solid #d9e0ea; border-radius: 8px; padding: 12px 14px; }
  div[data-testid="stMetricLabel"] { color: #667085; }
</style>
"""


st.markdown(CSS, unsafe_allow_html=True)


@st.cache_data
def load_data():
    calib_df = pd.read_csv(ROOT / "data_processed" / "base_calibration.csv")
    params_df = pd.read_csv(ROOT / "data_processed" / "parameters.csv")
    scenarios = pd.read_csv(ROOT / "outputs" / "scenario_results.csv")
    dictionary = pd.read_csv(ROOT / "data_processed" / "data_dictionary.csv")
    sources = pd.read_csv(ROOT / "data_processed" / "source_matrix.csv")
    calibration = {}
    for _, row in calib_df.iterrows():
        value = row["value"]
        try:
            calibration[row["variable"]] = float(value)
        except (TypeError, ValueError):
            calibration[row["variable"]] = value
    params = dict(zip(params_df["parameter"], params_df["value"].astype(float)))
    return calibration, params, scenarios, dictionary, sources


@st.cache_data(ttl=3600, show_spinner="Consultando series oficiales (TRM, FRED)...")
def get_live_overrides() -> dict:
    """Refresca TRM, Fed funds y Brent desde fuentes oficiales con cache 1h.

    Si una fuente falla, conserva el valor del snapshot. Devuelve dict con
    ``overrides`` (a aplicar sobre la calibracion) y ``status`` (banderas por
    serie).
    """
    snapshot = live_data.fetch_all_live()
    return {"overrides": dict(snapshot["overrides"]), "status": dict(snapshot["status"]), "fetched_at": snapshot["fetched_at"]}


@st.cache_data(ttl=86400, show_spinner="Descargando series historicas (Datos Abiertos + FRED)...")
def get_backtest_panel() -> pd.DataFrame:
    """Descarga TRM, Fed funds y Brent historicas y construye panel trimestral."""
    trm = live_data.fetch_trm_history()
    fed = live_data.fetch_fred_history("DFF")
    brent = live_data.fetch_fred_history("DCOILBRENTEU")
    return bt.build_exogenous_panel(trm, fed, brent)


def fmt(value: float, decimals: int = 2) -> str:
    return f"{value:,.{decimals}f}"


def fmt_delta(value: float, decimals: int = 2, suffix: str = "") -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value:,.{decimals}f}{suffix}"


def plot_theme(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        height=height,
        margin={"l": 20, "r": 24, "t": 40, "b": 28},
        paper_bgcolor="white",
        plot_bgcolor="white",
        font={"family": "Inter, Segoe UI, Arial", "color": "#172033"},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
            "font": {"size": 12},
        },
        hoverlabel={"bgcolor": "white", "font_size": 12},
    )
    fig.update_xaxes(showgrid=True, gridcolor="#edf1f6", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="#edf1f6", zeroline=False)
    return fig


def equilibrium_figure_main(
    calibration: dict[str, float],
    shock: Shock,
    params: dict[str, float],
    base_result: dict[str, float],
    sim_result: dict[str, float],
) -> go.Figure:
    """Diagrama IS*-LM* en plano (Y, TRM) para economia abierta pequena.

    IS* (azul): pendiente positiva (TRM ↑ = peso depreciado → NX ↑ → Y ↑).
    LM* (verde): vertical en el Y consistente con el mercado monetario dada la
    tasa local r y la oferta monetaria M.
    """
    base_rate = float(base_result["policy_rate_pct"])
    sim_rate = float(sim_result["policy_rate_pct"])
    y_base = float(base_result["gdp_real_cop_billion"])
    y_sim = float(sim_result["gdp_real_cop_billion"])
    trm_base = float(base_result["trm_cop_per_usd"])
    trm_sim = float(sim_result["trm_cop_per_usd"])

    span = max(abs(y_sim - y_base), 0.05 * y_base)
    y_min = min(y_base, y_sim) - 1.5 * span
    y_max = max(y_base, y_sim) + 1.5 * span

    ys, trms_base = curves.is_star_curve(calibration, Shock(), params, base_rate, y_min, y_max)
    _, trms_sim = curves.is_star_curve(calibration, shock, params, sim_rate, y_min, y_max)

    trm_floor = min(min(trms_base), min(trms_sim), trm_base, trm_sim)
    trm_ceil = max(max(trms_base), max(trms_sim), trm_base, trm_sim)
    trm_pad = max((trm_ceil - trm_floor) * 0.10, 50.0)
    trm_y_min = trm_floor - trm_pad
    trm_y_max = trm_ceil + trm_pad

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ys, y=trms_base, mode="lines", name="IS* base",
        line={"color": "#2563eb", "width": 2.6},
    ))
    fig.add_trace(go.Scatter(
        x=ys, y=trms_sim, mode="lines", name="IS* escenario",
        line={"color": "#2563eb", "width": 2.6, "dash": "dash"},
    ))
    fig.add_trace(go.Scatter(
        x=[y_base, y_base], y=[trm_y_min, trm_y_max], mode="lines", name="LM* base",
        line={"color": "#0f9f8f", "width": 2.6},
    ))
    fig.add_trace(go.Scatter(
        x=[y_sim, y_sim], y=[trm_y_min, trm_y_max], mode="lines", name="LM* escenario",
        line={"color": "#0f9f8f", "width": 2.6, "dash": "dash"},
    ))
    fig.add_trace(go.Scatter(
        x=[y_base], y=[trm_base], mode="markers+text",
        marker={"color": "#111827", "size": 12},
        text=["Base"], textposition="top right",
        showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=[y_sim], y=[trm_sim], mode="markers+text",
        marker={"color": "#dc2626", "size": 13, "symbol": "diamond"},
        text=["Escenario"], textposition="bottom right",
        showlegend=False,
    ))
    if abs(y_sim - y_base) + abs(trm_sim - trm_base) > 1e-6:
        fig.add_annotation(
            x=y_sim, y=trm_sim, ax=y_base, ay=trm_base,
            xref="x", yref="y", axref="x", ayref="y",
            showarrow=True, arrowhead=2, arrowcolor="#dc2626", arrowwidth=2,
        )

    fig.update_layout(
        xaxis_title="Y - PIB real trimestral (COP miles de millones, precios 2015)",
        yaxis_title="TRM (COP/USD) — sube = peso depreciado",
        hovermode="closest",
    )
    return plot_theme(fig, 520)


def model_components_figure(
    calibration: dict[str, float],
    params: dict[str, float],
) -> go.Figure:
    """Cuatro paneles que ilustran los bloques del modelo MF.

    Panel 1: I(r) - inversion como funcion de la tasa.
    Panel 2: S(Y) - ahorro privado como funcion del producto.
    Panel 3: NX(TRM) - exportaciones netas como funcion del tipo de cambio.
    Panel 4: IS* (Y, TRM) - la curva resultante.
    """
    from plotly.subplots import make_subplots
    c = curves.base_components(calibration)

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=(
            "1. Inversion: I = I0 (1 - b·(r - r0))",
            "2. Ahorro privado: S = Y - C(Y-T) - G",
            "3. Exportaciones netas: NX = X(TRM) - M(TRM, Y)",
            "4. Curva IS* resultante en (Y, TRM)",
        ),
        horizontal_spacing=0.13, vertical_spacing=0.20,
    )

    # Panel 1: I(r). Eje X = I, Eje Y = r
    n = 40
    r_min, r_max = c["rate0"] - 3, c["rate0"] + 3
    rates = [r_min + i * (r_max - r_min) / (n - 1) for i in range(n)]
    inv_curve = [c["i0"] * (1.0 - params["investment_rate_sensitivity"] * (r - c["rate0"])) for r in rates]
    fig.add_trace(go.Scatter(x=inv_curve, y=rates, mode="lines", line={"color": "#2563eb", "width": 2.5}, name="I(r)", showlegend=False), row=1, col=1)
    fig.add_hline(y=c["rate0"], line_dash="dot", line_color="#888", row=1, col=1)
    fig.add_annotation(x=c["i0"], y=c["rate0"], text="r₀", showarrow=False, xshift=15, yshift=10, row=1, col=1)
    fig.update_xaxes(title_text="I (COP bn)", row=1, col=1)
    fig.update_yaxes(title_text="r (%)", row=1, col=1)

    # Panel 2: S(Y)
    y_min, y_max = c["y0"] * 0.92, c["y0"] * 1.08
    ys = [y_min + i * (y_max - y_min) / (n - 1) for i in range(n)]
    s_curve = [(y - (c["c0"] + params["mpc"] * (y - c["y0"])) - c["g0"]) for y in ys]
    fig.add_trace(go.Scatter(x=ys, y=s_curve, mode="lines", line={"color": "#0f9f8f", "width": 2.5}, name="S(Y)", showlegend=False), row=1, col=2)
    s_at_y0 = c["y0"] - c["c0"] - c["g0"]
    fig.add_trace(go.Scatter(x=[c["y0"]], y=[s_at_y0], mode="markers", marker={"color": "#111827", "size": 9}, showlegend=False), row=1, col=2)
    fig.update_xaxes(title_text="Y (COP bn)", row=1, col=2)
    fig.update_yaxes(title_text="S (COP bn)", row=1, col=2)

    # Panel 3: NX(TRM)
    trm_min, trm_max = c["trm0"] * 0.85, c["trm0"] * 1.15
    trms = [trm_min + i * (trm_max - trm_min) / (n - 1) for i in range(n)]
    nx_curve = []
    for trm in trms:
        q = (trm / c["trm0"]) - 1
        xv = c["x0"] * (1 + params["eta_export_q"] * q)
        mv = c["m0"] * (1 - params["eta_import_q"] * q)
        nx_curve.append(xv - mv)
    fig.add_trace(go.Scatter(x=trms, y=nx_curve, mode="lines", line={"color": "#d97706", "width": 2.5}, name="NX(TRM)", showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=[c["trm0"]], y=[c["x0"] - c["m0"]], mode="markers", marker={"color": "#111827", "size": 9}, showlegend=False), row=2, col=1)
    fig.update_xaxes(title_text="TRM (COP/USD) — derecha = peso depreciado", row=2, col=1)
    fig.update_yaxes(title_text="NX (COP bn)", row=2, col=1)

    # Panel 4: IS* curve
    ys_is = [c["y0"] * 0.92 + i * (c["y0"] * 0.16) / (n - 1) for i in range(n)]
    is_trms = [curves.is_star_trm(calibration, Shock(), params, c["rate0"], y) for y in ys_is]
    fig.add_trace(go.Scatter(x=ys_is, y=is_trms, mode="lines", line={"color": "#dc2626", "width": 2.5}, name="IS*", showlegend=False), row=2, col=2)
    fig.add_trace(go.Scatter(x=[c["y0"]], y=[c["trm0"]], mode="markers", marker={"color": "#111827", "size": 9}, showlegend=False), row=2, col=2)
    fig.update_xaxes(title_text="Y (COP bn)", row=2, col=2)
    fig.update_yaxes(title_text="TRM (COP/USD)", row=2, col=2)

    fig.update_layout(height=700, template="plotly_white", margin={"l": 30, "r": 30, "t": 60, "b": 30}, font={"family": "Inter, Segoe UI, Arial", "color": "#172033"})
    return fig


def money_market_figure(
    calibration: dict[str, float],
    shock: Shock,
    params: dict[str, float],
    base_result: dict[str, float],
    sim_result: dict[str, float],
) -> go.Figure:
    """Mercado monetario en (M/P, r): oferta vertical, demanda L(r, Y) downward."""
    data = curves.money_market_data(calibration, shock, params, base_result, sim_result)
    rates = data["rates"]
    r_min, r_max = min(rates), max(rates)

    fig = go.Figure()
    # Demanda base
    fig.add_trace(go.Scatter(
        x=data["base_demand"], y=rates, mode="lines",
        name="Demanda L(r, Y) base", line={"color": "#2563eb", "width": 2.5},
    ))
    # Demanda escenario (puede coincidir con base si no hay choque a Y o policy)
    fig.add_trace(go.Scatter(
        x=data["sim_demand"], y=rates, mode="lines",
        name="Demanda L(r, Y) escenario", line={"color": "#2563eb", "width": 2.5, "dash": "dash"},
    ))
    # Oferta base (vertical)
    fig.add_trace(go.Scatter(
        x=[data["base_supply"], data["base_supply"]], y=[r_min, r_max], mode="lines",
        name="Oferta M/P base", line={"color": "#0f9f8f", "width": 2.5},
    ))
    # Oferta escenario
    fig.add_trace(go.Scatter(
        x=[data["sim_supply"], data["sim_supply"]], y=[r_min, r_max], mode="lines",
        name="Oferta M/P escenario", line={"color": "#0f9f8f", "width": 2.5, "dash": "dash"},
    ))
    # Equilibrios
    fig.add_trace(go.Scatter(
        x=[data["base_eq"][0]], y=[data["base_eq"][1]], mode="markers+text",
        marker={"color": "#111827", "size": 11},
        text=["Base"], textposition="top right", showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=[data["sim_eq"][0]], y=[data["sim_eq"][1]], mode="markers+text",
        marker={"color": "#dc2626", "size": 12, "symbol": "diamond"},
        text=["Escenario"], textposition="bottom right", showlegend=False,
    ))
    fig.update_layout(
        xaxis_title="M/P real (normalizado, base = 1.00)",
        yaxis_title="Tasa de interes domestica r (%)",
        hovermode="closest",
    )
    return plot_theme(fig, 460)


def ad_as_figure(
    calibration: dict[str, float],
    shock: Shock,
    params: dict[str, float],
    base_result: dict[str, float],
    sim_result: dict[str, float],
) -> go.Figure:
    """AD-AS en (Y, P): AS_SR horizontal, AS_LR vertical, AD downward."""
    data = curves.ad_as_data(calibration, shock, params, base_result, sim_result)
    prices = data["prices"]
    y_n = data["y_n"]
    base_ys = data["base_ad"]
    sim_ys = data["sim_ad"]

    y_min = min(min(base_ys), min(sim_ys), y_n) * 0.95
    y_max = max(max(base_ys), max(sim_ys), y_n) * 1.05

    fig = go.Figure()
    # AD base
    fig.add_trace(go.Scatter(
        x=base_ys, y=prices, mode="lines",
        name="AD base", line={"color": "#2563eb", "width": 2.5},
    ))
    # AD escenario
    fig.add_trace(go.Scatter(
        x=sim_ys, y=prices, mode="lines",
        name="AD escenario", line={"color": "#2563eb", "width": 2.5, "dash": "dash"},
    ))
    # AS corto plazo (horizontal en P=1.0, precios fijos)
    fig.add_trace(go.Scatter(
        x=[y_min, y_max], y=[1.0, 1.0], mode="lines",
        name="AS corto plazo (precios fijos)",
        line={"color": "#0f9f8f", "width": 2.5},
    ))
    # AS largo plazo (vertical en Y_n)
    fig.add_trace(go.Scatter(
        x=[y_n, y_n], y=[min(prices), max(prices)], mode="lines",
        name="AS largo plazo (Y_n)",
        line={"color": "#d97706", "width": 2.5, "dash": "dot"},
    ))
    # Equilibrios
    fig.add_trace(go.Scatter(
        x=[data["base_eq"][0]], y=[data["base_eq"][1]], mode="markers+text",
        marker={"color": "#111827", "size": 11},
        text=["Base"], textposition="top right", showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=[data["sim_eq"][0]], y=[data["sim_eq"][1]], mode="markers+text",
        marker={"color": "#dc2626", "size": 12, "symbol": "diamond"},
        text=["Escenario"], textposition="bottom right", showlegend=False,
    ))
    fig.update_layout(
        xaxis_title="Y - PIB real trimestral (COP miles de millones)",
        yaxis_title="Nivel de precios P (normalizado, base = 1.00)",
        hovermode="closest",
    )
    return plot_theme(fig, 460)


def impact_figure(calibration: dict[str, float], base_result: dict[str, float], sim_result: dict[str, float]) -> go.Figure:
    df = curves.impact_rows(calibration, base_result, sim_result)
    df["texto"] = df.apply(lambda r: f"{fmt_delta(r['impacto'], 2)} {r['unidad']}", axis=1)
    colors = ["#dc2626" if x > 0 else "#0f9f8f" if x < 0 else "#94a3b8" for x in df["impacto"]]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=df["variable"],
            x=df["impacto"],
            orientation="h",
            marker_color=colors,
            text=df["texto"],
            textposition="outside",
            hovertemplate="%{y}: %{text}<extra></extra>",
        )
    )
    fig.add_vline(x=0, line_width=1, line_color="#667085")
    fig.update_layout(
        xaxis_title="Cambio frente al escenario base",
        yaxis_title="",
        showlegend=False,
    )
    return plot_theme(fig, 410)


def comparison_table(calibration: dict[str, float], base_result: dict[str, float], sim_result: dict[str, float]) -> pd.DataFrame:
    return curves.comparison_rows(calibration, base_result, sim_result)


def active_shock_items(shock: Shock) -> list[str]:
    specs = [
        ("consumption_autonomous_pct", "Consumo autonomo (a)", "%", "Choque a C0; en perfecta aprecia el peso (IS izquierda en plano (Y, e))."),
        ("investment_autonomous_pct", "Inversion autonoma (h)", "%", "Choque a I0; mismo signo que choque a consumo autonomo."),
        ("government_spending_pct", "Gasto publico (G)", "%", "Aumenta demanda interna y desplaza IS\\* (en plano (Y, e), aprecia el peso)."),
        ("tax_pct_of_gdp", "Impuestos (T)", "% PIB", "Si sube, reduce ingreso disponible y desplaza IS\\* a la izquierda (deprecia)."),
        ("money_supply_pct", "Oferta monetaria M3", "%", "Expansion mueve LM\\* a la derecha (Y_LM mayor); en perfecta deprecia."),
        ("domestic_policy_rate_bp", "Tasa Banrep", "pbs", "Bajo movilidad imperfecta atrae capitales y aprecia; bajo perfecta queda anulada por UIP."),
        ("foreign_rate_bp", "Tasa Fed (r*)", "pbs", "Sube r* y por UIP la tasa local; LM se mueve, peso deprecia."),
        ("risk_premium_bp", "Prima de riesgo Colombia", "pbs", "Mayor prima exige mas retorno y deprecia."),
        ("oil_price_pct", "Precio Brent", "%", "Mayor petroleo mejora exportaciones y aprecia el peso."),
        ("nx_autonomous_pct", "NX autonomo (z, bm)", "% PIB", "Choque exogeno a NX: exportaciones autonomas, terminos de intercambio, barreras a importaciones, demanda externa."),
    ]
    items = []
    for field, label, unit, note in specs:
        value = curves.shock_value(shock, field)
        if abs(value) > 1e-9:
            items.append(f"**{label}:** {fmt_delta(value, 1)} {unit}. {note}")
    return items


def mechanism_items(base_result: dict[str, float], sim_result: dict[str, float]) -> list[str]:
    trm_delta = sim_result["trm_cop_per_usd"] - base_result["trm_cop_per_usd"]
    y_delta = sim_result["gdp_real_cop_billion"] - base_result["gdp_real_cop_billion"]
    rate_delta = sim_result["policy_rate_pct"] - base_result["policy_rate_pct"]
    ca_delta = sim_result["current_account_usd_m"] - base_result["current_account_usd_m"]

    trm_text = "depreciacion" if trm_delta > 0 else "apreciacion" if trm_delta < 0 else "sin cambio relevante"
    y_text = "mayor actividad" if y_delta > 0 else "menor actividad" if y_delta < 0 else "producto casi igual"
    rate_text = "sube" if rate_delta > 0 else "baja" if rate_delta < 0 else "no cambia"
    ca_text = "mejora cuenta corriente" if ca_delta > 0 else "deteriora cuenta corriente" if ca_delta < 0 else "cuenta corriente sin cambio"
    return [
        f"TRM: {fmt_delta(trm_delta, 2, ' COP')} ({fmt_delta(sim_result['trm_change_pct'], 2, '%')}) -> **{trm_text}**.",
        f"PIB real: {fmt_delta(y_delta, 1, ' COP bn')} -> **{y_text}** frente al base.",
        f"Tasa domestica {rate_text} {fmt_delta(rate_delta, 2, ' p.p.')}.",
        f"Cuenta corriente: {fmt_delta(ca_delta, 1, ' USD m')} -> **{ca_text}**.",
    ]


def bp_direction(value: float, neutral_band: float = 1e-6) -> str:
    if value > neutral_band:
        return "apreciacion"
    if value < -neutral_band:
        return "depreciacion"
    return "neutral"


def scenario_guardrails(base_result: dict[str, float], sim_result: dict[str, float]) -> list[str]:
    warnings = []
    if abs(sim_result["trm_change_pct"]) > 25:
        warnings.append(
            f"**Escenario extremo:** la TRM cambia {fmt_delta(sim_result['trm_change_pct'], 1, '%')}. Interpreta el resultado como prueba de sensibilidad, no como pronostico."
        )
    if abs(sim_result["output_gap_pct"]) > 8:
        warnings.append(
            f"**Brecha grande:** el producto cambia {fmt_delta(sim_result['output_gap_pct'], 1, '%')} frente al nivel base; puede estar fuera del rango donde una aproximacion lineal es confiable."
        )
    return warnings


def render_story(title: str, items: list[str], style: str = "info") -> None:
    if not items:
        items = ["No hay choques activos. Estas viendo el punto de calibracion base."]
    body = f"**{title}**\n\n" + "\n".join(f"- {item}" for item in items)
    if style == "warning":
        st.warning(body)
    else:
        st.info(body)


def control_slider(label: str, help_text: str, *args, **kwargs):
    return st.slider(label, *args, help=help_text, **kwargs)


def scale_shock(shock: Shock, factor: float) -> Shock:
    return Shock(**{field: float(getattr(shock, field)) * factor for field in Shock.__dataclass_fields__})


calibration_snapshot, params, scenarios_df, dictionary_df, sources_df = load_data()
live = get_live_overrides()
calibration = {**calibration_snapshot, **live["overrides"]}


def _live_label(series: str, fallback_date: str) -> str:
    info = live["status"].get(series, {})
    if info.get("ok"):
        return f"en vivo {info.get('date', '')}"
    return f"snapshot {fallback_date}"


trm_badge = _live_label("trm", calibration_snapshot.get("trm_latest_date", "n.d."))
fed_badge = _live_label("fed_funds", calibration_snapshot.get("foreign_rate_reference_date", "n.d."))
brent_badge = _live_label("brent", calibration_snapshot.get("oil_reference_date", "n.d."))


st.title("Modelo Mundell-Fleming para Colombia")
st.markdown(
    "Simulador de economia abierta pequena con tasa de cambio flexible. Cada choque mueve "
    "demanda agregada, mercado monetario, balance de pagos y TRM. **Mayor TRM = peso depreciado.**"
)

badge_cols = st.columns(5)
badge_cols[0].caption(f"**Cuentas nacionales:** {calibration.get('gdp_data_period', 'n.d.')} (snapshot)")
badge_cols[1].caption(f"**TRM:** {calibration.get('trm_cop_per_usd', 0):,.2f} COP/USD - {trm_badge}")
badge_cols[2].caption(f"**Fed funds:** {calibration.get('foreign_rate_pct', 0):.2f}% - {fed_badge}")
badge_cols[3].caption(f"**Brent:** USD {calibration.get('oil_brent_usd_per_barrel', 0):.2f} - {brent_badge}")
badge_cols[4].caption(f"**Refrescado:** {live['fetched_at']}")

if st.button("Refrescar datos en vivo", help="Re-consulta TRM (Datos Abiertos), Fed funds y Brent (FRED). Ignora la cache."):
    get_live_overrides.clear()
    st.rerun()


left, right = st.columns([0.31, 0.69], gap="large")

with left:
    st.subheader("Panel de choques")
    mobility = st.radio(
        "Movilidad de capitales",
        list(MOBILITY_OPTIONS),
        format_func=lambda key: MOBILITY_LABELS[key],
        horizontal=False,
        help="Perfecta = caso canonico (la tasa local se ancla a la externa). Imperfecta = calibracion empirica para Colombia.",
    )
    st.caption(MOBILITY_DESCRIPTIONS[mobility])
    st.caption("Usa el modo guiado para explorar rapido. Cambia a experto solo si quieres tocar cada supuesto.")
    mode = st.radio(
        "Modo de uso",
        ["Guiado", "Experto"],
        horizontal=True,
        help="Guiado prioriza claridad. Experto abre todos los sliders y parametros.",
    )
    scenario_name = st.selectbox(
        "1. Elige el choque",
        list(SCENARIOS.keys()),
        help="Carga un paquete de choques tipico. Luego puedes modificar cada slider manualmente.",
    )
    selected = SCENARIOS[scenario_name]
    st.caption(SCENARIO_MECHANISMS.get(scenario_name, "Escenario base sin choques."))

    if mode == "Guiado":
        intensity_options = {
            "Suave": 0.5,
            "Central": 1.0,
            "Fuerte": 1.75,
            "Estres": 2.75,
        }
        intensity_label = st.radio(
            "2. Escoge intensidad",
            list(intensity_options.keys()),
            index=1,
            horizontal=True,
            help="Multiplica el escenario preconfigurado. Estres es para sensibilidad, no pronostico.",
        )
        shock = scale_shock(selected, intensity_options[intensity_label])
        st.info(
            "**Modo guiado:** la app aplica el escenario elegido con la intensidad seleccionada. "
            "Para modificar una variable especifica, cambia a modo experto."
        )
    else:
        st.caption("Modo experto: 10 palancas que cubren todos los choques estandar del modelo y los relevantes para el caso colombiano.")
        with st.expander("Choques autonomos a la IS (a, h)", expanded=False):
            consumption_autonomous_pct = control_slider(
                "Consumo autonomo a (%)",
                "Choque a C0 (consumo autonomo). En el curso = a. Mueve la IS.",
                -30.0, 30.0, selected.consumption_autonomous_pct, 1.0,
            )
            investment_autonomous_pct = control_slider(
                "Inversion autonoma h (%)",
                "Choque a I0 (inversion autonoma). En el curso = h. Mueve la IS.",
                -40.0, 40.0, selected.investment_autonomous_pct, 1.0,
            )

        with st.expander("Politica fiscal", expanded=False):
            government_spending_pct = control_slider(
                "Gasto publico G (%)",
                "Cambio porcentual del consumo publico real. Empuja la curva IS.",
                -50.0, 50.0, selected.government_spending_pct, 1.0,
            )
            tax_pct_of_gdp = control_slider(
                "Impuestos T (% del PIB)",
                "Choque fiscal como porcentaje del PIB base. Al subir, reduce ingreso disponible.",
                -10.0, 10.0, selected.tax_pct_of_gdp, 0.25,
            )

        with st.expander("Politica monetaria", expanded=False):
            money_supply_pct = control_slider(
                "Oferta monetaria M3 (%)",
                "Expansion monetaria: en flexible deprecia y sube producto. Mecanismo central de Mundell-Fleming.",
                -50.0, 50.0, selected.money_supply_pct, 1.0,
            )
            domestic_policy_rate_bp = control_slider(
                "Tasa Banrep (pbs)",
                "100 pbs = 1 punto porcentual. En perfecta queda anulada por la paridad de intereses; en imperfecta aprecia/deprecia segun el signo.",
                -500.0, 700.0, selected.domestic_policy_rate_bp, 25.0,
            )

        with st.expander("Choques externos", expanded=False):
            foreign_rate_bp = control_slider(
                "Tasa Fed (pbs)",
                "Sube el rendimiento externo. Bajo UIP, deprecia el peso.",
                -500.0, 700.0, selected.foreign_rate_bp, 25.0,
            )
            risk_premium_bp = control_slider(
                "Prima de riesgo Colombia (pbs)",
                "Spread del CDS/EMBI Colombia vs Treasury. Mayor riesgo deprecia.",
                -300.0, 700.0, selected.risk_premium_bp, 25.0,
            )
            oil_price_pct = control_slider(
                "Precio Brent (%)",
                "Mayor Brent = mayores exportaciones colombianas (eta_oil_export aplicable).",
                -60.0, 60.0, selected.oil_price_pct, 2.0,
            )
            nx_autonomous_pct = control_slider(
                "NX autonomo (% del PIB)",
                "Choque autonomo a exportaciones netas. Resume terminos de intercambio, demanda externa y choques directos a X/M.",
                -5.0, 5.0, selected.nx_autonomous_pct, 0.25,
            )

        shock = Shock(
            consumption_autonomous_pct=consumption_autonomous_pct,
            investment_autonomous_pct=investment_autonomous_pct,
            government_spending_pct=government_spending_pct,
            tax_pct_of_gdp=tax_pct_of_gdp,
            money_supply_pct=money_supply_pct,
            domestic_policy_rate_bp=domestic_policy_rate_bp,
            foreign_rate_bp=foreign_rate_bp,
            risk_premium_bp=risk_premium_bp,
            oil_price_pct=oil_price_pct,
            nx_autonomous_pct=nx_autonomous_pct,
        )

base = simulate(calibration, Shock(), params, mobility=mobility)
sim = simulate(calibration, shock, params, mobility=mobility)


with right:
    st.subheader("Lectura rapida")
    st.info(
        "**Uso correcto:** esta herramienta no pronostica la TRM. Es una simulacion comparativa "
        "calibrada con un snapshot fijo (cuentas nacionales 2025Q4) mas series en vivo de TRM, Fed funds y Brent."
    )
    render_story("Choques activos", active_shock_items(shock))
    render_story("Mecanismo economico del escenario", mechanism_items(base, sim))
    guardrails = scenario_guardrails(base, sim)
    if guardrails:
        render_story("Alertas de interpretacion", guardrails, style="warning")

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric(
            "TRM simulada",
            f"{fmt(sim['trm_cop_per_usd'], 2)} COP/USD",
            fmt_delta(sim["trm_cop_per_usd"] - base["trm_cop_per_usd"], 2, " COP"),
            help="Aumento de TRM = depreciacion del peso. Es la variable central del simulador.",
        )
    with m2:
        st.metric(
            "Cambio TRM",
            f"{fmt_delta(sim['trm_change_pct'], 2, '%')}",
            "depreciacion" if sim["trm_change_pct"] > 0 else "apreciacion" if sim["trm_change_pct"] < 0 else "sin cambio",
            help="Variacion porcentual frente a la TRM base calibrada.",
        )
    with m3:
        st.metric(
            "Brecha producto",
            f"{fmt_delta(sim['output_gap_pct'], 2, '%')}",
            fmt_delta(sim["output_gap_pct"] - base["output_gap_pct"], 2, " p.p."),
            help="Cambio porcentual del PIB real frente al nivel base calibrado. Es mas interpretable que el nivel de PIB.",
        )
    with m4:
        st.metric(
            "Tasa domestica",
            f"{fmt(sim['policy_rate_pct'], 2)}%",
            fmt_delta(sim["policy_rate_pct"] - base["policy_rate_pct"], 2, " p.p."),
            help="Tasa del bloque monetario. Sube con choques contractivos o mayor brecha de producto; baja con expansion monetaria.",
        )

    m5, m6, m7, m8 = st.columns(4)
    with m5:
        st.metric(
            "Cuenta corriente",
            f"{fmt(sim['current_account_usd_m'], 1)} USD m",
            fmt_delta(sim["current_account_usd_m"] - base["current_account_usd_m"], 1, " USD m"),
            help="Saldo corriente aproximado. Mejora con exportaciones, petroleo, demanda externa o depreciacion real.",
        )
    with m6:
        st.metric(
            "Cuenta financiera",
            f"{fmt(sim['financial_account_inflow_usd_m'], 1)} USD m",
            fmt_delta(sim["financial_account_inflow_usd_m"] - base["financial_account_inflow_usd_m"], 1, " USD m"),
            help="Entrada neta de capitales. Responde al diferencial de tasas, riesgo y flujos exogenos.",
        )
    with m7:
        st.metric(
            "Balance pagos",
            f"{fmt(sim['balance_of_payments_gap_usd_m'], 1)} USD m",
            bp_direction(sim["balance_of_payments_gap_usd_m"]),
            help="Positivo = presion de apreciacion; negativo = presion de depreciacion.",
        )
    with m8:
        st.metric(
            "PIB real trimestral",
            f"{fmt(sim['gdp_real_cop_billion'], 1)} COP bn",
            fmt_delta(sim["gdp_real_cop_billion"] - base["gdp_real_cop_billion"], 1, " COP bn"),
            help="PIB real trimestral en COP miles de millones a precios constantes de 2015. Dato base: cuentas nacionales DANE.",
        )

    st.caption(
        "**Sobre el PIB real:** el valor mostrado es el nivel **trimestral** de cuentas nacionales en "
        "COP miles de millones, precios constantes de 2015. No es PIB anual ni pesos corrientes."
    )

    tab_summary, tab_eqs, tab_curves, tab_compare, tab_horizon, tab_table, tab_backtest, tab_data = st.tabs(
        ["Impacto", "Ecuaciones de equilibrio", "Curvas del modelo", "Base vs simulado", "Corto vs largo plazo", "Cuentas nacionales y proyecciones", "Backtesting", "Datos y supuestos"]
    )

    with tab_summary:
        st.subheader("Cambios frente al escenario base")
        st.caption("Cada barra es el cambio % o p.p. frente al base. Verde = apreciacion / mejora externa; rojo = depreciacion / deterioro.")
        st.plotly_chart(impact_figure(calibration, base, sim), width="stretch")

    with tab_eqs:
        st.subheader("Ecuaciones de equilibrio: caso base vs caso impactado")
        st.markdown(
            "Las tablas muestran cada bloque del modelo con su forma simbolica, los valores numericos del **caso "
            "base** (sin choques) y los del **caso impactado** (con el choque seleccionado). La columna `delta` es "
            "la diferencia simulado - base; `delta_pct` es el cambio porcentual. "
            "Una identidad (Y = C + I + G + NX + residuo) se verifica al final del bloque."
        )

        st.markdown("### 1. Identidad de gasto agregado")
        df_is = eqs.is_identity_rows(base, sim, calibration)
        df_is_disp = df_is.copy()
        for col in ["base", "escenario", "delta"]:
            df_is_disp[col] = df_is_disp[col].map(lambda v: f"{v:,.1f}")
        df_is_disp["delta_pct"] = df_is_disp["delta_pct"].map(lambda v: "n/a" if pd.isna(v) else f"{v:+.2f}%")
        st.dataframe(df_is_disp, width="stretch", hide_index=True)

        st.markdown("### 2. Bloque monetario (LM) y paridad descubierta (UIP)")
        df_mon = eqs.monetary_block_rows(base, sim, calibration, shock, params)
        df_mon_disp = df_mon.copy()
        for col in ["base", "escenario", "delta"]:
            df_mon_disp[col] = df_mon_disp[col].map(lambda v: f"{v:,.4f}")
        df_mon_disp["delta_pct"] = df_mon_disp["delta_pct"].map(lambda v: "n/a" if pd.isna(v) else f"{v:+.2f}%")
        st.dataframe(df_mon_disp, width="stretch", hide_index=True)

        st.markdown("### 3. Bloque externo (TRM, balanza de pagos)")
        df_ext = eqs.external_block_rows(base, sim, calibration)
        df_ext_disp = df_ext.copy()
        for col in ["base", "escenario", "delta"]:
            df_ext_disp[col] = df_ext_disp[col].map(lambda v: f"{v:,.2f}")
        df_ext_disp["delta_pct"] = df_ext_disp["delta_pct"].map(lambda v: "n/a" if pd.isna(v) else f"{v:+.2f}%")
        st.dataframe(df_ext_disp, width="stretch", hide_index=True)

        st.markdown("### 4. Verificacion de identidad")
        check = eqs.identity_check(base, sim)
        c1, c2, c3 = st.columns(3)
        c1.metric("Y simulado (LHS)", f"{check['lhs']:,.1f}")
        c2.metric("C+I+G+NX (RHS)", f"{check['rhs_no_residuo']:,.1f}")
        c3.metric("Discrepancia estadistica", f"{check['residuo']:,.1f}", f"{check['drift']:+.4f} vs base")
        st.caption(
            "**Discrepancia estadistica DANE:** el residuo no es exactamente cero porque las cuentas nacionales "
            f"publicadas tienen un sesgo de cierre de {check['residuo_base']:,.1f} COP bn (≈ "
            f"{(check['residuo_base']/check['lhs']*100):.3f}% del PIB). "
            "Es comun en cualquier sistema de cuentas nacionales y no se debe al modelo. **Lo que importa es la "
            "linea inferior del tercer recuadro:** indica cuanto se mueve esa discrepancia entre el caso base y el "
            "caso impactado. Si la cifra es cercana a cero, el modelo preserva la identidad correctamente."
        )

    with tab_curves:
        st.subheader("Equilibrio IS*-LM* en el plano (Y, TRM)")
        st.caption(
            "**IS\\*** (azul, pendiente positiva): mas TRM = peso depreciado = mas NX = mas Y demandado por el gasto. "
            "**LM\\*** (verde, vertical): el Y consistente con el mercado monetario para la tasa local r y la oferta "
            "monetaria M. Linea solida = base; linea punteada = escenario. La flecha roja muestra el movimiento del "
            "equilibrio."
        )
        st.plotly_chart(equilibrium_figure_main(calibration, shock, params, base, sim), width="stretch")
        with st.expander("Como leer esta grafica"):
            st.markdown(
                "- **Politica fiscal expansiva (+G):** IS\\* sube (para cada Y, requiere menor TRM para que NX baje "
                "y el gasto cuadre). LM\\* no se mueve. Equilibrio: Y constante, TRM cae (peso aprecia).\n"
                "- **Politica monetaria expansiva (+M):** LM\\* se mueve a la derecha (Y_LM mayor para r dada). "
                "IS\\* sin cambio. Equilibrio: Y sube, TRM sube (peso depreciado).\n"
                "- **Choque a r externa (Fed/riesgo):** sube r local via UIP. IS\\* baja (la I cae) y LM\\* se "
                "mueve (Y consistente con la nueva r). Equilibrio: Y y TRM ajustan en la direccion del choque.\n"
                "- **Choque real (Brent, NX_aut):** desplaza IS\\* directamente. LM\\* sin cambio."
            )

        st.divider()
        st.subheader("Mercado monetario en (M/P, r)")
        st.caption(
            "**Demanda L(r, Y)** (azul, pendiente negativa): mayor r = mayor costo de oportunidad de tener saldos "
            "reales = menor demanda. **Oferta M/P** (verde, vertical): el banco central fija M; con precios fijos "
            "P, M/P queda determinado. Equilibrio: tasa que iguala oferta y demanda. Choque a M desplaza la oferta; "
            "choque a Y o a tasa de politica desplaza la demanda. M/P se normaliza con base = 1.00."
        )
        st.plotly_chart(money_market_figure(calibration, shock, params, base, sim), width="stretch")
        with st.expander("Como leer esta grafica"):
            st.markdown(
                "- **Choque +10% M:** la oferta vertical se mueve a 1.10. Bajo movilidad perfecta la tasa queda "
                "anclada por UIP, asi que el mercado monetario se acomoda con desplazamiento de la demanda (Y↑). "
                "Bajo imperfecta la tasa cae.\n"
                "- **Choque a Y (fiscal en imperfecta):** la demanda L se desplaza a la derecha (mayor Y demanda "
                "mas saldos reales para transacciones). En equilibrio la tasa sube.\n"
                "- **Choque a tasa Banrep (imperfecta):** la regla del banco central impone una tasa mayor; la "
                "demanda baja a esa tasa, presionando ajuste de la oferta o de Y."
            )

        st.divider()
        st.subheader("Demanda y oferta agregadas en (Y, P)")
        st.caption(
            "**AD** (azul, pendiente negativa): para cada P, el Y consistente con IS-LM. Mayor P reduce M/P real, "
            "sube la tasa (en imperfecta) o reduce Y demandado por LM. **AS corto plazo** (verde, horizontal): "
            "precios fijos en P=1.0. **AS largo plazo** (ambar, vertical): producto natural Y_n. Equilibrio SR = "
            "AD ∩ AS_SR; equilibrio LR = AD ∩ AS_LR."
        )
        st.plotly_chart(ad_as_figure(calibration, shock, params, base, sim), width="stretch")
        with st.expander("Como leer esta grafica"):
            st.markdown(
                "- En **corto plazo** (este modelo): los precios estan fijos en P=1, asi que el equilibrio queda "
                "donde AD cruza la AS horizontal. Y puede desviarse de Y_n.\n"
                "- En **largo plazo**: los precios suben hasta que Y vuelve a Y_n. Choques de demanda no afectan "
                "Y en el LR, solo P.\n"
                "- **Politica monetaria expansiva (+M):** AD se mueve a la derecha. SR: Y sube, P fijo. "
                "LR: P sube proporcional, Y vuelve a Y_n.\n"
                "- **Politica fiscal en perfecta:** la AD apenas se mueve (en MF flexible perfecta el ajuste va "
                "via TRM, no via Y). En imperfecta si se mueve."
            )

        st.divider()
        with st.expander("Derivacion de la curva IS* (4 paneles)", expanded=False):
            st.caption(
                "Cuatro bloques que muestran como se construye la curva IS\\* del primer grafico: "
                "(1) la inversion responde a la tasa, (2) el ahorro privado depende del ingreso, "
                "(3) las exportaciones netas dependen del tipo de cambio, (4) combinando los tres se "
                "obtiene IS\\* en el plano (Y, TRM). Esta figura es estatica (no responde a los choques "
                "de los sliders) y sirve solo para entender los componentes."
            )
            st.plotly_chart(model_components_figure(calibration, params), width="stretch")

    with tab_compare:
        st.subheader("Tabla legible de base vs simulado")
        st.caption("Cada variable en su unidad natural; columna de lectura para evitar mezclar escalas.")
        table = comparison_table(calibration, base, sim)
        display_table = table.copy()
        for col in ["base", "simulado", "cambio", "cambio_pct"]:
            display_table[col] = display_table[col].map(lambda x: "" if pd.isna(x) else fmt(x, 2))
        st.dataframe(display_table, width="stretch", hide_index=True)

        st.subheader("Escenarios preconfigurados")
        scenario_view = scenarios_df.copy()
        numeric_cols = scenario_view.select_dtypes(include="number").columns
        for col in numeric_cols:
            scenario_view[col] = scenario_view[col].map(lambda x: fmt(x, 2))
        st.dataframe(scenario_view, width="stretch", hide_index=True)

    with tab_horizon:
        st.subheader("Corto plazo (este modelo) vs Largo plazo")
        st.markdown(
            "**Punto de partida.** Este simulador implementa el **modelo Mundell-Fleming de "
            "corto plazo**. Asume **precios fijos**, por lo que el producto Y puede desviarse de "
            "su nivel natural Y_n ante choques de politica. Las curvas IS\\*-LM\\* que ves operan en "
            "este marco. La movilidad perfecta de capitales es el caso canonico puro; la "
            "imperfecta agrega tasa local endogena y mecanismo de ajuste por presion de balanza "
            "de pagos."
        )
        st.markdown(
            "**Largo plazo (referencia teorica).** En el LP los precios ajustan: Y vuelve a Y_n "
            "y el tipo de cambio real absorbe los desbalances. Resultados clave que cambian:"
        )
        st.markdown(
            "- **Politica monetaria es neutral en LR** (clasica neutralidad): un choque a M solo "
            "mueve precios y tipo de cambio nominal, no Y. En SR si mueve Y porque los precios "
            "no han ajustado todavia.\n"
            "- **Choques externos** (Fed, prima de riesgo) tienen efecto solo via la inversion "
            "(`I` responde a `r = r* + risk`). En SR amplifican el efecto via la respuesta de la "
            "LM (Y se desvia de Y_n).\n"
            "- **Politica fiscal** mueve NX en ambos plazos (en SR perfecta: ya da el resultado "
            "canonico; en SR imperfecta: tambien mueve Y; en LR: solo mueve NX, Y queda en Y_n)."
        )

        st.markdown("---")
        st.markdown(f"**Comparacion para el choque activo (modo {MOBILITY_LABELS[mobility]})**")
        st.caption(
            "El SR mostrado abajo respeta el modo de movilidad seleccionado en el panel izquierdo. "
            "El LR siempre asume movilidad perfecta como referente teorico estandar."
        )

        sr_result = sim
        lr_result = simulate_long_run(calibration, shock, params)

        comp_rows = [
            ("PIB real (COP bn)", sr_result["gdp_real_cop_billion"], lr_result["gdp_real_cop_billion"]),
            ("Brecha producto (%)", sr_result["output_gap_pct"], lr_result["output_gap_pct"]),
            ("TRM (COP/USD)", sr_result["trm_cop_per_usd"], lr_result["trm_cop_per_usd"]),
            ("Cambio TRM (%)", sr_result["trm_change_pct"], lr_result["trm_change_pct"]),
            ("Tasa domestica (%)", sr_result["policy_rate_pct"], lr_result["policy_rate_pct"]),
            ("Consumo real (COP bn)", sr_result["private_consumption_real_cop_billion"], lr_result["private_consumption_real_cop_billion"]),
            ("Inversion real (COP bn)", sr_result["investment_real_cop_billion"], lr_result["investment_real_cop_billion"]),
            ("NX real (COP bn)", sr_result["net_exports_real_cop_billion"], lr_result["net_exports_real_cop_billion"]),
            ("Cuenta corriente (USD m)", sr_result["current_account_usd_m"], lr_result["current_account_usd_m"]),
        ]
        comp_df = pd.DataFrame(
            [{"Variable": v, "Corto plazo": sr_v, "Largo plazo": lr_v, "SR - LR": sr_v - lr_v}
             for v, sr_v, lr_v in comp_rows]
        )
        for col in ["Corto plazo", "Largo plazo", "SR - LR"]:
            comp_df[col] = comp_df[col].map(lambda x: fmt(x, 2))
        st.dataframe(comp_df, width="stretch", hide_index=True)

        st.info(
            "**Como leer las diferencias.** Si SR != LR, el choque produce desviaciones transitorias del "
            "equilibrio de pleno empleo que el ajuste de precios eventualmente corrige. La columna "
            "'SR - LR' es una medida cruda de cuanto trabajo le toca al ajuste de precios. "
            "Para choque monetario puro debe converger a 0 en LR (neutralidad). Para choques fiscales "
            "puros las diferencias deberian ser pequenas (la transmision via NX domina en ambos plazos)."
        )

    with tab_table:
        st.subheader("Cuentas nacionales y proyecciones a 5 anios")
        st.caption(
            "5 anios historicos (DANE) + 5 anios proyectados (modelo). Los flujos historicos suman los 4 trimestres "
            "del anio; las proyecciones aplican el % de cambio del modelo al ultimo anio observado para evitar saltos "
            "artificiales por estacionalidad. Sin Monte Carlo: cada anio es solucion deterministica del escenario."
        )

        scenario_keys = list(PROJECTION_SCENARIOS.keys())
        proj_scenario_name = st.selectbox(
            "Escenario de proyeccion (5 anios)",
            scenario_keys,
            index=0,
            help="Cada escenario aplica un choque sostenido durante 5 anios.",
        )
        st.caption(PROJECTION_SCENARIOS[proj_scenario_name].description)

        try:
            quarterly_df = pd.read_csv(ROOT / "data_processed" / "quarterly_master.csv")
            last_observed_year = int(quarterly_df["year"].dropna().max())
            projection_df = project_scenario(
                calibration,
                proj_scenario_name,
                parameters=params,
                mobility=mobility,
                base_year=last_observed_year,
            )
            consolidated = build_consolidated_table(
                quarterly_df,
                calibration,
                projection_df,
                last_observed_year=last_observed_year,
                history_years=5,
            )
        except Exception as exc:
            st.error(f"No se pudo construir la tabla: {exc}")
        else:
            display = consolidated.copy()
            for col in display.columns:
                display[col] = display[col].map(lambda x: "n/d" if pd.isna(x) else f"{x:,.1f}")
            st.dataframe(display, width="stretch")

            csv_bytes = to_csv_bytes(consolidated)
            st.download_button(
                "Descargar CSV",
                data=csv_bytes,
                file_name=f"MF_Colombia_{mobility}_{proj_scenario_name.replace(' ', '_')}.csv",
                mime="text/csv",
                help="Tabla completa en CSV UTF-8 con BOM (compatible con Excel en espanol).",
            )

    with tab_backtest:
        st.subheader("Backtesting contra realidad colombiana")
        st.caption(
            "Para cada trimestre, alimentamos el modelo con el cambio observado de Fed funds y Brent, y comparamos "
            "el cambio % de TRM predicho contra el observado. La cache se renueva cada 24 horas."
        )

        if st.button("Correr backtest", help="Descarga TRM (Datos Abiertos) + Fed funds y Brent (FRED) y corre el modelo trimestre a trimestre."):
            try:
                panel = get_backtest_panel()
            except Exception as exc:
                st.error(f"No se pudo descargar el panel: {exc}")
                panel = pd.DataFrame()

            if panel.empty:
                st.warning("No se obtuvo panel historico. Posiblemente FRED esta inalcanzable desde el host. Intenta de nuevo en unos minutos.")
            else:
                missing_optional = [c for c in ("fed_funds_pct", "brent_usd") if c not in panel.columns]
                if missing_optional:
                    st.warning(
                        f"Panel parcial: faltan series **{', '.join(missing_optional)}** (probable: FRED inalcanzable "
                        "desde el servidor). El backtest sigue corriendo, pero los choques exogenos correspondientes "
                        "se tratan como cero. El RMSE refleja entonces la varianza inexplicada de la TRM."
                    )
                bt_df = bt.run_backtest(panel, calibration, parameters=params, mobility=mobility)
                m = bt.metrics(bt_df)

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Trimestres", f"{m['n']}")
                c2.metric("RMSE (% TRM)", f"{m['rmse']:.2f}")
                c3.metric("MAE (% TRM)", f"{m['mae']:.2f}")
                c4.metric("Correlacion", f"{m['correlation']:.2f}" if not pd.isna(m['correlation']) else "n/d")

                fig_ts = go.Figure()
                fig_ts.add_trace(go.Scatter(x=bt_df["quarter"], y=bt_df["observed_trm_change_pct"], name="Observado", mode="lines+markers", line={"color": "#172033"}))
                fig_ts.add_trace(go.Scatter(x=bt_df["quarter"], y=bt_df["predicted_trm_change_pct"], name="Predicho", mode="lines+markers", line={"color": "#dc2626", "dash": "dash"}))
                fig_ts.update_layout(xaxis_title="Trimestre", yaxis_title="Cambio % TRM", hovermode="x unified")
                st.plotly_chart(plot_theme(fig_ts, 380), width="stretch")

                fig_sc = go.Figure()
                fig_sc.add_trace(go.Scatter(x=bt_df["observed_trm_change_pct"], y=bt_df["predicted_trm_change_pct"], mode="markers", marker={"color": "#2563eb", "size": 8}, text=bt_df["quarter"], hovertemplate="%{text}: obs %{x:.2f}%, pred %{y:.2f}%<extra></extra>"))
                rng = max(abs(bt_df["observed_trm_change_pct"]).max(), abs(bt_df["predicted_trm_change_pct"]).max(), 1.0) * 1.1
                fig_sc.add_trace(go.Scatter(x=[-rng, rng], y=[-rng, rng], mode="lines", line={"color": "#94a3b8", "dash": "dot"}, name="45 grados", showlegend=False))
                fig_sc.update_layout(xaxis_title="Cambio % TRM observado", yaxis_title="Cambio % TRM predicho", hovermode="closest")
                st.plotly_chart(plot_theme(fig_sc, 380), width="stretch")

                with st.expander("Tabla detallada por trimestre"):
                    bt_view = bt_df.copy()
                    for col in bt_view.select_dtypes(include="number").columns:
                        bt_view[col] = bt_view[col].map(lambda x: fmt(x, 2))
                    st.dataframe(bt_view, width="stretch", hide_index=True)

                st.info(
                    "**Lectura:** el modelo es estatico-comparativo y solo incluye Fed funds y Brent como exogenos en este backtest. "
                    "Episodios donde el modelo subestima la depreciacion (ej. 2020Q2 COVID, 2022 inflacion global, 2023 ruido politico) son limites del modelo, no bugs. "
                    "La prima de riesgo Colombia y choques de oferta domesticos no entran al backtest."
                )
        else:
            st.info("Pulsa 'Correr backtest' para descargar series historicas y ver predicho vs observado. La descarga puede tomar 5-15 segundos la primera vez.")

    with tab_data:
        st.subheader("Calibracion base")
        st.info(
            "**Lectura de unidades:** variables reales del DANE en COP miles de millones a precios constantes de 2015. "
            "Saldos externos en USD millones. Tasas en % anual."
        )
        sc1, sc2, sc3 = st.columns(3)
        sc1.markdown("**Datos observados**\n\nTRM, cuentas nacionales, inflacion y tasa de politica desde fuentes publicas oficiales.")
        sc2.markdown("**Proxies documentados**\n\nPrima de riesgo, Brent, M3 y reservas vienen como proxy si la serie directa no esta integrada.")
        sc3.markdown("**Parametros supuestos**\n\nElasticidades y sensibilidades son calibrables; el modo experto explora la incertidumbre.")
        base_rows = [
            ["TRM", calibration["trm_cop_per_usd"], "COP/USD", calibration["trm_latest_date"], "Observada"],
            ["PIB real trimestral", calibration["gdp_real_cop_billion"], "COP bn, precios 2015", calibration["gdp_data_period"], "DANE"],
            ["PIB nominal trimestral", calibration["gdp_nominal_cop_billion"], "COP bn corrientes", calibration["gdp_data_period"], "DANE"],
            ["Consumo privado real", calibration["private_consumption_real_cop_billion"], "COP bn, precios 2015", calibration["gdp_data_period"], "DANE"],
            ["Inversion real", calibration["investment_real_cop_billion"], "COP bn, precios 2015", calibration["gdp_data_period"], "DANE"],
            ["Exportaciones reales", calibration["exports_real_cop_billion"], "COP bn, precios 2015", calibration["gdp_data_period"], "DANE"],
            ["Importaciones reales", calibration["imports_real_cop_billion"], "COP bn, precios 2015", calibration["gdp_data_period"], "DANE"],
            ["Tasa politica", calibration["policy_rate_pct"], "%", calibration["policy_rate_reference_date"], "BanRep"],
            ["Inflacion anual", calibration["inflation_yoy_pct"], "%", calibration["inflation_reference_date"], "DANE"],
            ["Fed funds efectiva", calibration["foreign_rate_pct"], "%", calibration["foreign_rate_reference_date"], "Federal Reserve"],
            ["Prima de riesgo proxy", calibration["risk_premium_pct"], "%", calibration["risk_premium_reference_date"], "Proxy publico"],
            ["Brent proxy", calibration["oil_brent_usd_per_barrel"], "USD/barril", calibration["oil_reference_date"], "Proxy publico"],
            ["M3 proxy", calibration["money_supply_m3_cop_billion"], "COP bn", calibration["money_supply_reference_date"], "Proxy publico"],
            ["Reservas proxy", calibration["reserves_usd_m"], "USD m", calibration["reserves_reference_date"], "Proxy publico"],
        ]
        cal_table = pd.DataFrame(base_rows, columns=["variable", "valor", "unidad", "fecha", "fuente"])
        cal_table["valor"] = cal_table["valor"].map(lambda x: fmt(float(x), 2) if isinstance(x, (int, float)) else x)
        st.dataframe(cal_table, width="stretch", hide_index=True)

        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Diccionario")
            st.dataframe(dictionary_df, width="stretch", hide_index=True)
        with col_b:
            st.subheader("Fuentes")
            st.dataframe(sources_df, width="stretch", hide_index=True)


st.caption("Datos publicos DANE, Banco de la Republica, Superfinanciera/Datos Abiertos y Federal Reserve | Calibracion 2026-04-24")
