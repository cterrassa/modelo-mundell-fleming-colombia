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


MOBILITY_LABELS = {
    "perfecta": "Movilidad perfecta (textbook Mankiw)",
    "imperfecta": "Movilidad imperfecta (calibracion Colombia)",
}
MOBILITY_DESCRIPTIONS = {
    "perfecta": (
        "Caso canonico: la tasa domestica queda anclada por la paridad de intereses. "
        "La politica fiscal NO mueve el producto (ΔY = 0); todo el ajuste pasa por la TRM. "
        "La politica monetaria SI es efectiva."
    ),
    "imperfecta": (
        "Calibracion empirica para Colombia: capitales con movilidad finita y prima de riesgo. "
        "La politica fiscal SI mueve el producto y la TRM se ajusta parcialmente. "
        "Cercano a la realidad, pero no es el resultado canonico de Mundell-Fleming."
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


def equilibrium_figure(
    calibration: dict[str, float],
    shock: Shock,
    base_params: dict[str, float],
    scenario_params: dict[str, float],
    base_result: dict[str, float],
    sim_result: dict[str, float],
    mobility: str = "perfecta",
) -> go.Figure:
    data = curves.curve_data(calibration, shock, base_params, scenario_params, base_result, sim_result, mobility=mobility)
    gaps = data["gaps"]
    fig = go.Figure()
    styles = [
        ("Base", "solid", "base", 0.75),
        ("Escenario", "dash", "scenario", 1.0),
    ]
    colors = {"IS": "#2563eb", "LM": "#0f9f8f", "BP=0": "#d97706"}
    for label, dash, data_key, opacity in styles:
        for curve_name in ["IS", "LM", "BP=0"]:
            fig.add_trace(
                go.Scatter(
                    x=gaps,
                    y=data[data_key][curve_name],
                    mode="lines",
                    name=f"{curve_name} {label}",
                    line={"color": colors[curve_name], "dash": dash, "width": 2.7},
                    opacity=opacity,
                )
            )

    fig.add_trace(
        go.Scatter(
            x=[base_result["output_gap_pct"], sim_result["output_gap_pct"]],
            y=[base_result["policy_rate_pct"], sim_result["policy_rate_pct"]],
            mode="lines",
            name="Movimiento del equilibrio",
            line={"color": "#111827", "width": 1.8, "dash": "dot"},
            showlegend=False,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[base_result["output_gap_pct"]],
            y=[base_result["policy_rate_pct"]],
            mode="markers+text",
            name="Equilibrio base",
            marker={"color": "#111827", "size": 11},
            text=["Base"],
            textposition="top center",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[sim_result["output_gap_pct"]],
            y=[sim_result["policy_rate_pct"]],
            mode="markers+text",
            name="Equilibrio simulado",
            marker={"color": "#dc2626", "size": 13, "symbol": "diamond"},
            text=["Simulado"],
            textposition="bottom center",
        )
    )
    fig.add_vline(x=0, line_width=1, line_dash="dot", line_color="#9ca3af")
    fig.update_layout(
        xaxis_title="Brecha del producto frente al nivel base (%)",
        yaxis_title="Tasa de interes domestica (%)",
        hovermode="x unified",
    )
    fig.add_annotation(
        x=sim_result["output_gap_pct"],
        y=sim_result["policy_rate_pct"],
        text="nuevo equilibrio",
        showarrow=True,
        arrowhead=2,
        ax=30 if sim_result["output_gap_pct"] <= base_result["output_gap_pct"] else -30,
        ay=-35,
        bgcolor="white",
        bordercolor="#d9e0ea",
        borderwidth=1,
    )
    return plot_theme(fig, 560)


def exchange_adjustment_figure(
    calibration: dict[str, float],
    shock: Shock,
    base_params: dict[str, float],
    scenario_params: dict[str, float],
    base_result: dict[str, float],
    sim_result: dict[str, float],
) -> go.Figure:
    data = curves.exchange_pressure_data(calibration, shock, base_params, scenario_params, base_result, sim_result)
    trms = data["trms"]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=trms,
            y=data["base"],
            mode="lines",
            name="Presion externa base",
            line={"color": "#4b5563", "width": 2.8},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=trms,
            y=data["scenario"],
            mode="lines",
            name="Presion externa escenario",
            line={"color": "#dc2626", "width": 2.8, "dash": "dash"},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[base_result["trm_cop_per_usd"], sim_result["trm_cop_per_usd"]],
            y=[base_result["balance_of_payments_gap_usd_m"], sim_result["balance_of_payments_gap_usd_m"]],
            mode="lines+markers+text",
            name="TRM base -> simulada",
            line={"color": "#111827", "dash": "dot", "width": 1.8},
            marker={"color": ["#111827", "#dc2626"], "size": [10, 13], "symbol": ["circle", "diamond"]},
            text=["Base", "Simulado"],
            textposition=["top center", "bottom center"],
        )
    )
    fig.add_hline(y=0, line_width=1, line_dash="dot", line_color="#6b7280")
    fig.update_layout(
        xaxis_title="TRM (COP/USD). Derecha = depreciacion del peso",
        yaxis_title="Balance de pagos / presion externa (USD m)",
        hovermode="x unified",
    )
    fig.add_annotation(
        x=sim_result["trm_cop_per_usd"],
        y=sim_result["balance_of_payments_gap_usd_m"],
        text="TRM simulada",
        showarrow=True,
        arrowhead=2,
        ax=-35,
        ay=-35,
        bgcolor="white",
        bordercolor="#d9e0ea",
        borderwidth=1,
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


def trm_contribution_figure(
    calibration: dict[str, float],
    shock: Shock,
    base_params: dict[str, float],
    scenario_params: dict[str, float],
    base_result: dict[str, float],
    sim_result: dict[str, float],
) -> go.Figure:
    df = curves.trm_contribution_rows(calibration, shock, scenario_params, base_result, sim_result)
    df["texto"] = df["puntos_pct_trm"].map(lambda value: fmt_delta(value, 2, " p.p."))
    colors = ["#dc2626" if x > 0 else "#0f9f8f" if x < 0 else "#94a3b8" for x in df["puntos_pct_trm"]]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=df["factor"],
            x=df["puntos_pct_trm"],
            orientation="h",
            marker_color=colors,
            text=df["texto"],
            textposition="outside",
            hovertemplate="%{y}: %{text}<extra></extra>",
        )
    )
    fig.add_vline(x=0, line_width=1, line_color="#667085")
    fig.update_layout(
        xaxis_title="Contribucion aproximada al cambio de TRM (puntos porcentuales)",
        yaxis_title="",
        showlegend=False,
    )
    return plot_theme(fig, 430)


def comparison_table(calibration: dict[str, float], base_result: dict[str, float], sim_result: dict[str, float]) -> pd.DataFrame:
    return curves.comparison_rows(calibration, base_result, sim_result)


def active_shock_items(shock: Shock, sensitivity_scale: float) -> list[str]:
    specs = [
        ("government_spending_pct", "Gasto publico (G)", "%", "Aumenta demanda interna y mueve IS a la derecha."),
        ("tax_pct_of_gdp", "Impuestos (T)", "% PIB", "Si sube, reduce ingreso disponible y mueve IS a la izquierda."),
        ("money_supply_pct", "Oferta monetaria M3", "%", "Expansion baja la tasa compatible con LM y deprecia."),
        ("domestic_policy_rate_bp", "Tasa Banrep", "pbs", "Bajo movilidad imperfecta atrae capitales y aprecia; bajo perfecta queda anulada por UIP."),
        ("foreign_rate_bp", "Tasa Fed", "pbs", "Sube el rendimiento externo y deprecia el peso."),
        ("risk_premium_bp", "Prima de riesgo Colombia", "pbs", "Mayor prima exige mas retorno y deprecia."),
        ("oil_price_pct", "Precio Brent", "%", "Mayor petroleo mejora exportaciones colombianas y aprecia."),
        ("nx_autonomous_pct", "NX autonomo", "% PIB", "Choque exogeno a exportaciones netas (terminos de intercambio, demanda externa, X/M directos)."),
    ]
    items = []
    for field, label, unit, note in specs:
        value = curves.shock_value(shock, field)
        if abs(value) > 1e-9:
            items.append(f"**{label}:** {fmt_delta(value, 1)} {unit}. {note}")
    if abs(sensitivity_scale - 1.0) > 1e-9:
        items.append(
            f"**Sensibilidad cambiaria:** {fmt(sensitivity_scale, 2)}x. Amplifica la reaccion de la TRM (solo modo imperfecta)."
        )
    return items


def mechanism_items(base_result: dict[str, float], sim_result: dict[str, float]) -> list[str]:
    trm_delta = sim_result["trm_cop_per_usd"] - base_result["trm_cop_per_usd"]
    y_delta = sim_result["gdp_real_cop_billion"] - base_result["gdp_real_cop_billion"]
    rate_delta = sim_result["policy_rate_pct"] - base_result["policy_rate_pct"]
    bp_delta = sim_result["balance_of_payments_gap_usd_m"] - base_result["balance_of_payments_gap_usd_m"]

    trm_text = "depreciacion" if trm_delta > 0 else "apreciacion" if trm_delta < 0 else "sin cambio relevante"
    y_text = "mayor actividad" if y_delta > 0 else "menor actividad" if y_delta < 0 else "producto casi igual"
    rate_text = "sube" if rate_delta > 0 else "baja" if rate_delta < 0 else "no cambia"
    bp_text = "mejora la presion externa" if bp_delta > 0 else "deteriora la presion externa" if bp_delta < 0 else "mantiene el balance externo"
    return [
        f"La TRM cambia {fmt_delta(trm_delta, 2, ' COP')} ({fmt_delta(sim_result['trm_change_pct'], 2, '%')}): lectura central = **{trm_text}**.",
        f"El producto se mueve {fmt_delta(y_delta, 1, ' COP bn')}: el escenario implica **{y_text}** frente al nivel base.",
        f"La tasa domestica {rate_text} {fmt_delta(rate_delta, 2, ' p.p.')}; esto afecta inversion, demanda de dinero y flujos de capital.",
        f"El balance de pagos cambia {fmt_delta(bp_delta, 1, ' USD m')}: **{bp_text}** en el bloque externo.",
    ]


def bp_direction(value: float, neutral_band: float = 1e-6) -> str:
    if value > neutral_band:
        return "apreciacion"
    if value < -neutral_band:
        return "depreciacion"
    return "neutral"


def scenario_guardrails(base_result: dict[str, float], sim_result: dict[str, float], sensitivity_scale: float) -> list[str]:
    warnings = []
    if abs(sim_result["trm_change_pct"]) > 25:
        warnings.append(
            f"**Escenario extremo:** la TRM cambia {fmt_delta(sim_result['trm_change_pct'], 1, '%')}. Interpreta el resultado como prueba de sensibilidad, no como pronostico."
        )
    if abs(sim_result["output_gap_pct"]) > 8:
        warnings.append(
            f"**Brecha grande:** el producto cambia {fmt_delta(sim_result['output_gap_pct'], 1, '%')} frente al nivel base; puede estar fuera del rango donde una aproximacion lineal es confiable."
        )
    if sensitivity_scale != 1.0:
        warnings.append(
            f"**Sensibilidad cambiaria ajustada:** {fmt(sensitivity_scale, 2)}x es un parametro exploratorio, no un dato observado."
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
        help="Perfecta = caso textbook (Mankiw cap. 13). Imperfecta = calibracion empirica para Colombia.",
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
        exchange_sensitivity_scale = control_slider(
            "3. Sensibilidad de TRM",
            "Parametro exploratorio: 1x es calibracion central; mas alto hace mas visible la reaccion cambiaria.",
            0.5,
            3.0,
            1.0,
            0.05,
        )
        shock = scale_shock(selected, intensity_options[intensity_label])
        st.info(
            "**Modo guiado:** la app aplica el escenario elegido con la intensidad seleccionada. "
            "Para modificar una variable especifica, cambia a modo experto."
        )
    else:
        st.caption("Modo experto: 8 palancas con respaldo en Mankiw cap. 13 y datos colombianos. Bloques arrancan cerrados.")
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

        exchange_sensitivity_scale = control_slider(
            "Sensibilidad cambiaria (solo imperfecta)",
            "Multiplica la respuesta de TRM al gap de UIP y al residual de balanza de pagos. Sin efecto en perfecta.",
            0.25, 3.0, 1.0, 0.05,
        )

        shock = Shock(
            government_spending_pct=government_spending_pct,
            tax_pct_of_gdp=tax_pct_of_gdp,
            money_supply_pct=money_supply_pct,
            domestic_policy_rate_bp=domestic_policy_rate_bp,
            foreign_rate_bp=foreign_rate_bp,
            risk_premium_bp=risk_premium_bp,
            oil_price_pct=oil_price_pct,
            nx_autonomous_pct=nx_autonomous_pct,
        )

scenario_params = curves.scaled_exchange_params(params, exchange_sensitivity_scale)
base = simulate(calibration, Shock(), params, mobility=mobility)
sim = simulate(calibration, shock, scenario_params, mobility=mobility)


with right:
    st.subheader("Lectura rapida")
    st.info(
        "**Uso correcto:** esta herramienta no pronostica la TRM. Es una simulacion comparativa "
        "calibrada con un snapshot fijo (cuentas nacionales 2025Q4) mas series en vivo de TRM, Fed funds y Brent."
    )
    render_story("Choques activos", active_shock_items(shock, exchange_sensitivity_scale))
    render_story("Mecanismo economico del escenario", mechanism_items(base, sim))
    guardrails = scenario_guardrails(base, sim, exchange_sensitivity_scale)
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

    tab_summary, tab_curves, tab_compare, tab_horizon, tab_table, tab_backtest, tab_data = st.tabs(
        ["Impacto", "Curvas del modelo", "Base vs simulado", "Corto vs largo plazo", "Cuentas nacionales y proyecciones", "Backtesting", "Datos y supuestos"]
    )

    with tab_summary:
        st.subheader("Mapa de impactos")
        st.caption("Cada barra es el cambio frente al escenario base, expresado en unidades comparables o normalizadas.")
        st.plotly_chart(impact_figure(calibration, base, sim), width="stretch")

        st.subheader("Que explica el cambio de la TRM")
        st.caption("Descomposicion aproximada por factor. Rojo presiona depreciacion; verde presiona apreciacion.")
        st.plotly_chart(trm_contribution_figure(calibration, shock, params, scenario_params, base, sim), width="stretch")

    with tab_curves:
        st.subheader("Equilibrio IS-LM-BP")
        st.caption(
            "IS (azul) = demanda agregada. LM (verde-azulado) = mercado monetario. BP=0 (ambar) = equilibrio externo. "
            "Linea solida = base; linea punteada = escenario."
        )
        st.plotly_chart(equilibrium_figure(calibration, shock, params, scenario_params, base, sim, mobility=mobility), width="stretch")
        with st.expander("Como leer esta grafica"):
            st.write(
                "Si la IS se mueve a la derecha, hay mas demanda para cada tasa. "
                "Si la LM se mueve hacia abajo, hay mas liquidez o menor tasa compatible. "
                "Si BP=0 se desplaza, cambia la tasa necesaria para equilibrar cuenta corriente y cuenta financiera. "
                "El punto rojo es el equilibrio que resulta de los sliders."
            )

        st.subheader("TRM y presion externa")
        st.caption(
            "Eje horizontal: TRM (a la derecha = depreciacion). Eje vertical: balance externo (sobre cero = presion de apreciacion). "
            "La curva punteada muestra como el choque mueve la presion externa."
        )
        st.plotly_chart(
            exchange_adjustment_figure(calibration, shock, params, scenario_params, base, sim),
            width="stretch",
        )

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
        st.subheader("Corto plazo (este modelo) vs Largo plazo (Mankiw cap. 6)")
        st.markdown(
            "**Punto de partida.** Este simulador implementa el **modelo Mundell-Fleming de "
            "corto plazo** (Mankiw cap. 13). Asume **precios fijos**, por lo que el producto Y "
            "puede desviarse de su nivel natural Y_n ante choques de politica. Las curvas IS-LM-BP "
            "que ves operan en este marco. La movilidad perfecta de capitales es el caso textbook "
            "puro; la imperfecta agrega una pendiente positiva a la BP."
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
            "El LR siempre asume movilidad perfecta porque es el referente teorico de Mankiw cap. 6."
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
