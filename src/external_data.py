"""Descarga de series externas para calibracion (uso OFFLINE, no en el deploy).

Fuentes verificadas como alcanzables desde el entorno de desarrollo (a
diferencia de FRED, que falla por DNS):
- World Bank Pink Sheet (precios de commodities, .xlsx mensual).
- World Bank WDI API (PIB real de socios comerciales, JSON anual).

Construye series trimestrales de commodities relevantes para la canasta
exportadora colombiana (petroleo Brent, carbon colombiano, cafe, oro, niquel)
y un indice ponderado. Se usa para calibrar la elasticidad de exportaciones
del modelo (resuelve el signo equivocado por variable omitida). El resultado
se guarda en data_processed/commodities_quarterly.csv para reproducibilidad;
el modelo desplegado NO descarga esto en runtime.

Run: python src/external_data.py
"""

from __future__ import annotations

import io
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data_processed" / "commodities_quarterly.csv"

PINK_SHEET_URL = (
    "https://www.worldbank.org/content/dam/Worldbank/GEP/"
    "GEPcommodities/CMO-Historical-Data-Monthly.xlsx"
)

# Columnas (0-indexed) en la hoja "Monthly Prices" del Pink Sheet.
COMMODITY_COLS = {"brent": 2, "coal": 6, "coffee": 13, "gold": 72, "nickel": 70}

# Pesos aproximados de la canasta exportadora de commodities de Colombia
# (participacion relativa entre estos 5 bienes en exportaciones de bienes,
# promedio ~2015-2024). Documentados como aproximados; se normalizan a 1.
COLOMBIA_COMMODITY_WEIGHTS = {"brent": 0.55, "coal": 0.25, "coffee": 0.10, "gold": 0.08, "nickel": 0.02}

HTTP_TIMEOUT = 90


def _parse_pink_date(raw) -> tuple[int, int] | None:
    """Soporta los dos formatos de fecha del Pink Sheet: texto 'YYYYMmm' y
    objetos datetime (el archivo mezcla ambos segun el periodo)."""
    if raw is None:
        return None
    if hasattr(raw, "year") and hasattr(raw, "month"):
        return int(raw.year), int(raw.month)
    s = str(raw)
    if "M" in s:
        try:
            y, m = s.split("M")
            return int(y), int(m)
        except ValueError:
            return None
    return None


def parse_commodities_quarterly(source, year_min: int = 2004, year_max: int = 2025) -> pd.DataFrame:
    """Parsea el Pink Sheet (ruta a .xlsx o bytes) a commodities trimestrales.

    Separado del fetch de red para poder usar un archivo ya descargado (en
    entornos donde Python no tiene DNS pero curl si, se descarga con curl y se
    parsea aqui).
    """
    import openpyxl

    wb = openpyxl.load_workbook(source, read_only=True, data_only=True)
    ws = wb["Monthly Prices"]

    recs = []
    for row in ws.iter_rows(min_row=8, values_only=True):
        ym = _parse_pink_date(row[0])
        if ym is None:
            continue
        y, m = ym
        if y < year_min or y > year_max:
            continue
        rec = {"year": y, "q": (m - 1) // 3 + 1}
        for name, ci in COMMODITY_COLS.items():
            try:
                rec[name] = float(row[ci])
            except (TypeError, ValueError):
                rec[name] = np.nan
        recs.append(rec)

    cm = pd.DataFrame(recs)
    cmq = cm.groupby(["year", "q"]).mean(numeric_only=True).reset_index()
    cmq["period"] = cmq["year"].astype(str) + "Q" + cmq["q"].astype(str)

    w = COLOMBIA_COMMODITY_WEIGHTS
    wsum = sum(w.values())
    cmq["commodity_idx"] = np.exp(sum((w[k] / wsum) * np.log(cmq[k]) for k in w))
    return cmq


def fetch_commodities_quarterly(year_min: int = 2004, year_max: int = 2025) -> pd.DataFrame:
    """Descarga el Pink Sheet por red (requiere DNS en Python) y parsea.

    En entornos sin DNS en Python (p.ej. esta maquina de desarrollo), usar
    curl para descargar y luego parse_commodities_quarterly(ruta).
    """
    req = urllib.request.Request(PINK_SHEET_URL, headers={"User-Agent": "Mozilla/5.0 (MF-Colombia-Calib/1.0)"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        raw = resp.read()
    return parse_commodities_quarterly(io.BytesIO(raw), year_min, year_max)


def fetch_partner_gdp_annual(countries: str = "USA;CHN;PAN;ECU;MEX;BRA;PER", year_min: int = 2004) -> pd.DataFrame:
    """PIB real anual de socios (World Bank WDI, NY.GDP.MKTP.KD)."""
    import json

    url = (
        f"https://api.worldbank.org/v2/country/{countries}/indicator/"
        f"NY.GDP.MKTP.KD?format=json&per_page=20000&date={year_min}:2025"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (MF-Colombia-Calib/1.0)"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    rows = []
    for rec in payload[1] or []:
        if rec.get("value") is not None:
            rows.append({"country": rec["countryiso3code"], "year": int(rec["date"]), "gdp": float(rec["value"])})
    return pd.DataFrame(rows)


def main() -> None:
    import sys

    # Si se pasa una ruta local (archivo descargado con curl), parsear de ahi.
    if len(sys.argv) > 1:
        cmq = parse_commodities_quarterly(sys.argv[1])
    else:
        cmq = fetch_commodities_quarterly()
    cmq.to_csv(OUT, index=False)
    print(f"Commodities trimestrales: {len(cmq)} filas ({cmq['period'].iloc[0]} - {cmq['period'].iloc[-1]})")
    print(f"Guardado en {OUT}")


if __name__ == "__main__":
    main()
