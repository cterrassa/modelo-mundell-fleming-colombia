"""Backtesting del modelo Mundell-Fleming contra la realidad colombiana.

Procedimiento:
1. Tomar la serie historica trimestral de TRM (Datos Abiertos) y de exogenos
   externos (Fed funds, Brent) desde FRED.
2. Para cada trimestre, calcular el cambio observado de los exogenos respecto
   al trimestre anterior.
3. Alimentar el modelo con ese cambio y obtener el cambio % de TRM predicho.
4. Comparar contra el cambio % de TRM observado.
5. Reportar RMSE, MAE, correlacion, y un dataframe predicho-vs-observado.

Limitaciones que aceptamos honestamente:
- El modelo es estatico-comparativo: cada periodo es independiente, no acumula
  desviaciones. Esto es deliberado per la prompt.
- No incluye episodios de oferta puros (e.g., COVID, paro 2021).
- La prima de riesgo no entra al backtest porque no hay serie publica fiable.
"""

from __future__ import annotations

import math
from typing import Mapping

import pandas as pd

from mf_model import Shock, simulate


def aggregate_quarterly(daily_df: pd.DataFrame, label: str) -> pd.DataFrame:
    """Promedia una serie diaria a trimestres (frecuencia QE = quarter-end)."""
    if daily_df is None or daily_df.empty:
        return pd.DataFrame(columns=["quarter", label])
    df = daily_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    quarterly = df["value"].resample("QE").mean().to_frame(label).reset_index()
    quarterly["quarter"] = quarterly["date"].dt.to_period("Q").astype(str)
    return quarterly[["quarter", label]]


def build_exogenous_panel(
    trm_history: pd.DataFrame | None,
    fed_history: pd.DataFrame | None,
    brent_history: pd.DataFrame | None,
) -> pd.DataFrame:
    """Une TRM, Fed funds y Brent a frecuencia trimestral."""
    panel = pd.DataFrame()
    if trm_history is not None and not trm_history.empty:
        panel = aggregate_quarterly(trm_history, "trm")
    if fed_history is not None and not fed_history.empty:
        fed_q = aggregate_quarterly(fed_history, "fed_funds_pct")
        panel = panel.merge(fed_q, on="quarter", how="outer") if not panel.empty else fed_q
    if brent_history is not None and not brent_history.empty:
        brent_q = aggregate_quarterly(brent_history, "brent_usd")
        panel = panel.merge(brent_q, on="quarter", how="outer") if not panel.empty else brent_q
    return panel.dropna().sort_values("quarter").reset_index(drop=True)


REQUIRED_PANEL_COLUMNS = ("quarter", "trm")
OPTIONAL_PANEL_COLUMNS = ("fed_funds_pct", "brent_usd")
MIN_QUARTERS_FOR_BACKTEST = 4


def run_backtest(
    panel: pd.DataFrame,
    calibration: Mapping[str, float],
    parameters: Mapping[str, float] | None = None,
    mobility: str = "imperfecta",
) -> pd.DataFrame:
    """Para cada periodo t, predice el cambio % de TRM respecto a t-1 y compara.

    Asume que los exogenos del modelo son la diferencia entre t y t-1.
    Devuelve DataFrame con cambios observados y predichos por periodo.

    Tolera columnas opcionales ausentes (si FRED no esta disponible, el panel
    solo tiene TRM y los choques exogenos se asumen 0). En ese caso el modelo
    siempre predice 0% y el RMSE refleja la varianza no explicada de la TRM.

    Raises ValueError si faltan columnas requeridas o si el panel tiene
    menos de MIN_QUARTERS_FOR_BACKTEST trimestres (datos insuficientes para
    backtest significativo).
    """
    if panel.empty:
        return pd.DataFrame()

    missing_required = [c for c in REQUIRED_PANEL_COLUMNS if c not in panel.columns]
    if missing_required:
        raise ValueError(f"Panel incompleto, faltan columnas requeridas: {missing_required}.")

    if len(panel) < MIN_QUARTERS_FOR_BACKTEST:
        raise ValueError(
            f"Panel insuficiente: {len(panel)} trimestres. "
            f"Se requieren al menos {MIN_QUARTERS_FOR_BACKTEST} para un backtest significativo."
        )

    has_fed = "fed_funds_pct" in panel.columns
    has_brent = "brent_usd" in panel.columns

    rows = []
    for i in range(1, len(panel)):
        prev = panel.iloc[i - 1]
        cur = panel.iloc[i]

        if has_fed and pd.notna(prev["fed_funds_pct"]) and pd.notna(cur["fed_funds_pct"]):
            delta_fed_bp = (float(cur["fed_funds_pct"]) - float(prev["fed_funds_pct"])) * 100.0
        else:
            delta_fed_bp = 0.0

        if has_brent and pd.notna(prev["brent_usd"]) and pd.notna(cur["brent_usd"]):
            prev_brent = float(prev["brent_usd"])
            delta_oil_pct = ((float(cur["brent_usd"]) - prev_brent) / prev_brent) * 100.0 if prev_brent != 0 else 0.0
        else:
            delta_oil_pct = 0.0

        shock = Shock(foreign_rate_bp=delta_fed_bp, oil_price_pct=delta_oil_pct)
        result = simulate(calibration, shock, parameters, mobility=mobility)
        predicted_pct = float(result["trm_change_pct"])

        prev_trm = float(prev["trm"])
        observed_pct = ((float(cur["trm"]) - prev_trm) / prev_trm) * 100.0 if prev_trm != 0 else 0.0

        rows.append({
            "quarter": cur["quarter"],
            "delta_fed_bp": delta_fed_bp,
            "delta_oil_pct": delta_oil_pct,
            "observed_trm_change_pct": observed_pct,
            "predicted_trm_change_pct": predicted_pct,
            "residual_pct": observed_pct - predicted_pct,
        })
    return pd.DataFrame(rows)


def metrics(backtest_df: pd.DataFrame) -> dict[str, float]:
    """Calcula RMSE, MAE y correlacion entre observado y predicho."""
    if backtest_df.empty:
        return {"n": 0, "rmse": float("nan"), "mae": float("nan"), "correlation": float("nan")}
    diff = backtest_df["observed_trm_change_pct"] - backtest_df["predicted_trm_change_pct"]
    rmse = math.sqrt((diff ** 2).mean())
    mae = diff.abs().mean()
    obs = backtest_df["observed_trm_change_pct"]
    pred = backtest_df["predicted_trm_change_pct"]
    if obs.std() == 0 or pred.std() == 0:
        corr = float("nan")
    else:
        corr = obs.corr(pred)
    return {
        "n": int(len(backtest_df)),
        "rmse": float(rmse),
        "mae": float(mae),
        "correlation": float(corr),
        "mean_observed": float(obs.mean()),
        "mean_predicted": float(pred.mean()),
    }
