"""Fetchers para datos macroeconomicos en tiempo real.

Cada funcion intenta descargar la observacion mas reciente desde una fuente
publica oficial (Datos Abiertos Colombia para TRM, FRED para series externas).
Si falla por red, parsing o cualquier excepcion, devuelve ``None`` y la app
sigue usando el snapshot del repositorio.
"""

from __future__ import annotations

import io
import urllib.request
from datetime import datetime, timezone
from typing import TypedDict

import pandas as pd


HTTP_TIMEOUT_SECONDS = 8


class LiveSeries(TypedDict):
    """Resultado de un fetch en vivo."""
    label: str
    value: float
    date: str
    source: str


class LiveSnapshot(TypedDict):
    """Resultado consolidado del intento de refresh."""
    fetched_at: str
    overrides: dict[str, float]
    status: dict[str, dict[str, str | bool]]


def _http_get_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; MF-Colombia-Live/1.0)",
            "Accept": "text/csv,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_trm() -> LiveSeries | None:
    """TRM diaria oficial (Superfinanciera) via Datos Abiertos / Socrata."""
    try:
        url = "https://www.datos.gov.co/resource/32sa-8pi3.csv?$limit=5&$order=vigenciadesde%20DESC"
        df = pd.read_csv(io.StringIO(_http_get_text(url)))
        if df.empty or "valor" not in df.columns:
            return None
        latest = df.iloc[0]
        return LiveSeries(
            label="trm",
            value=float(latest["valor"]),
            date=str(latest["vigenciadesde"])[:10],
            source="Datos Abiertos Colombia / Superfinanciera",
        )
    except Exception:
        return None


def _fetch_fred_csv(series_id: str) -> tuple[float, str] | None:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    df = pd.read_csv(io.StringIO(_http_get_text(url)))
    if df.shape[1] < 2 or df.empty:
        return None
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    value_col = next((c for c in df.columns if c != "date"), None)
    if value_col is None:
        return None
    df = df[df[value_col].astype(str).str.strip() != "."]
    if df.empty:
        return None
    latest = df.iloc[-1]
    try:
        return float(latest[value_col]), str(latest["date"])
    except (TypeError, ValueError):
        return None


def fetch_fed_funds() -> LiveSeries | None:
    """Tasa de fondos federales efectiva diaria (FRED, serie DFF)."""
    try:
        result = _fetch_fred_csv("DFF")
        if result is None:
            return None
        value, date = result
        return LiveSeries(label="fed_funds", value=value, date=date, source="FRED (DFF)")
    except Exception:
        return None


def fetch_brent() -> LiveSeries | None:
    """Precio del crudo Brent diario (FRED / EIA, serie DCOILBRENTEU)."""
    try:
        result = _fetch_fred_csv("DCOILBRENTEU")
        if result is None:
            return None
        value, date = result
        return LiveSeries(label="brent", value=value, date=date, source="FRED / EIA (DCOILBRENTEU)")
    except Exception:
        return None


SERIES_TO_CALIBRATION_KEYS: dict[str, tuple[str, str]] = {
    "trm": ("trm_cop_per_usd", "trm_latest_date"),
    "fed_funds": ("foreign_rate_pct", "foreign_rate_reference_date"),
    "brent": ("oil_brent_usd_per_barrel", "oil_reference_date"),
}


def fetch_fred_history(series_id: str) -> pd.DataFrame | None:
    """Descarga la serie completa de FRED como DataFrame con columnas date, value.

    Util para backtesting historico. Usa el mismo timeout que las demas calls.
    """
    try:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        df = pd.read_csv(io.StringIO(_http_get_text(url)))
        if df.shape[1] < 2 or df.empty:
            return None
        df = df.copy()
        df.columns = [str(c).strip().lower() for c in df.columns]
        value_col = next((c for c in df.columns if c != "date"), None)
        if value_col is None:
            return None
        df = df[df[value_col].astype(str).str.strip() != "."]
        df["date"] = pd.to_datetime(df["date"])
        df["value"] = pd.to_numeric(df[value_col], errors="coerce")
        return df[["date", "value"]].dropna()
    except Exception:
        return None


def fetch_trm_history() -> pd.DataFrame | None:
    """Descarga toda la TRM diaria desde Datos Abiertos. ~10k filas."""
    try:
        url = "https://www.datos.gov.co/resource/32sa-8pi3.csv?$limit=20000&$order=vigenciadesde%20ASC"
        df = pd.read_csv(io.StringIO(_http_get_text(url)))
        if df.empty or "valor" not in df.columns:
            return None
        df = df.rename(columns={"valor": "value", "vigenciadesde": "date"})
        df["date"] = pd.to_datetime(df["date"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        return df[["date", "value"]].dropna()
    except Exception:
        return None


def fetch_all_live() -> LiveSnapshot:
    """Intenta descargar todas las series. Devuelve overrides + status."""
    fetchers = {
        "trm": fetch_trm,
        "fed_funds": fetch_fed_funds,
        "brent": fetch_brent,
    }
    overrides: dict[str, float] = {}
    status: dict[str, dict[str, str | bool]] = {}
    for label, fetcher in fetchers.items():
        series = fetcher()
        value_key, date_key = SERIES_TO_CALIBRATION_KEYS[label]
        if series is None:
            status[label] = {"ok": False, "source": "snapshot"}
            continue
        overrides[value_key] = series["value"]
        overrides[date_key] = series["date"]
        status[label] = {
            "ok": True,
            "date": series["date"],
            "source": series["source"],
        }
    return LiveSnapshot(
        fetched_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        overrides=overrides,
        status=status,
    )
