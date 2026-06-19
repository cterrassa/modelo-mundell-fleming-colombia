"""Series externas para calibracion (uso OFFLINE, no en el deploy).

Catalogo de fuentes ALCANZABLES por curl (el Python local no resuelve DNS, pero
curl si). Resultado de una busqueda exhaustiva que confirmo cada serie con
HTTP 200 y cobertura real. Todas las de FRED se descargan como CSV sin API key:
    https://fred.stlouisfed.org/graph/fredgraph.csv?id=SERIESID

Como el Python local no tiene DNS, el flujo es: descargar con curl a un
directorio (por defecto .fredtmp/), y parsear los CSV locales con este modulo.

    # 1) descargar (Bash):
    for ID in POILBREUSDM PCOALAUUSDM PCOFFOTMUSDM PNICKUSDM PMETAINDEXM \
              GDPC1 CLVMNACSCAB1GQDE NGDPRSAXDCBRQ NGDPRSAXDCMXQ; do
      curl -sS -o ".fredtmp/$ID.csv" "https://fred.stlouisfed.org/graph/fredgraph.csv?id=$ID"
    done
    # 2) construir los CSV procesados:
    python src/external_data.py .fredtmp

Escribe data_processed/commodities_quarterly.csv y foreign_demand_quarterly.csv.
El modelo desplegado NO descarga nada de esto en runtime.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_COMMODITIES = ROOT / "data_processed" / "commodities_quarterly.csv"
OUT_FOREIGN = ROOT / "data_processed" / "foreign_demand_quarterly.csv"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"


# Catalogo de series confirmadas por curl (HTTP 200, cobertura verificada).
# Cada entrada: descripcion, frecuencia, cobertura observada en la verificacion.
SERIES_CATALOG = {
    # --- Commodities (FRED, IMF PCPS), mensual USD, ~1992 -> 2026-05 ---
    "POILBREUSDM": "Petroleo Brent (IMF PCPS), mensual",
    "PCOALAUUSDM": "Carbon termico Australia/Newcastle (proxy carbon colombiano), mensual",
    "PCOFFOTMUSDM": "Cafe arabica Other Milds (proxy Colombian Milds), mensual",
    "PNICKUSDM": "Niquel (ferroniquel Cerro Matoso), mensual",
    "PMETAINDEXM": "Indice global de metales (proxy imperfecto de oro), mensual",
    "PALLFNFINDEXM": "Indice IMF de todos los commodities, mensual",
    "PNRGINDEXM": "Indice IMF de energia, mensual",
    # --- PIB real de socios (demanda externa) ---
    "GDPC1": "PIB real EE.UU. (chained 2017 USD, SA), trimestral",
    "CLVMNACSCAB1GQDE": "PIB real Alemania (proxy UE), trimestral",
    "NGDPRSAXDCBRQ": "PIB real Brasil (BRL const, SA), trimestral",
    "NGDPRSAXDCMXQ": "PIB real Mexico (MXN const, SA), trimestral",
    # --- Bloque cambiario / monetario / riesgo (disponibles para extension futura) ---
    "RBCOBIS": "ITCR/REER Colombia broad (BIS), mensual -> 2026-05",
    "COLIR3TIB01STM": "Tasa interbancaria 3m Colombia (proxy politica), mensual -> 2026-05",
    "COLIRLTLT01STM": "Bono gobierno 10a Colombia, mensual -> 2026-05",
    "DGS10": "UST 10a (para diferencial soberano), diaria",
    "BAMLEMCBPIOAS": "Spread credito EM (proxy EMBI/prima de riesgo), diaria",
}
# Otras fuentes confirmadas no-FRED:
#   TRM oficial diaria (Banrep via Socrata, AL PRESENTE):
#     https://www.datos.gov.co/resource/32sa-8pi3.csv?$limit=50000
#   PIB anual 8 socios (incluye China/Peru/Ecuador/Panama, hasta 2024):
#     https://api.worldbank.org/v2/country/USA;CHN;PAN;ECU;BRA;MEX;PER;DEU/indicator/NY.GDP.MKTP.KD?format=json
#   Terminos de intercambio Colombia (WDI, anual, ancla validacion, hasta 2023):
#     https://api.worldbank.org/v2/country/COL/indicator/TT.PRI.MRCH.XD.WD?format=json
# NO alcanzable por curl: precio de oro puro (LBMA eliminada de FRED 2025-05),
#   carbon colombiano especifico, cafe 'Colombian Milds' separado, PIB trimestral
#   de China/Peru/Ecuador/Panama, y los pesos bilaterales de exportacion (WITS/
#   Comtrade/OEC con DNS bloqueado). Ver docs/calibracion_ols.md.

# Pesos de la canasta exportadora colombiana para el indice de commodities
# (participacion aproximada; petroleo y carbon dominan).
COMMODITY_WEIGHTS = {"oil": 0.50, "coal": 0.27, "coffee": 0.12, "nickel": 0.05, "metal": 0.06}

# Pesos de socios en exportaciones de Colombia (WITS 2023, via WebSearch; no
# curl-confirmados — ver docs). Renormalizados entre los 4 socios con PIB
# trimestral en FRED.
PARTNER_WEIGHTS = {"us": 0.28, "de": 0.08, "br": 0.038, "mx": 0.033}

COMMODITY_FILES = {
    "oil": "POILBREUSDM", "coal": "PCOALAUUSDM", "coffee": "PCOFFOTMUSDM",
    "nickel": "PNICKUSDM", "metal": "PMETAINDEXM",
}
PARTNER_FILES = {
    "us": "GDPC1", "de": "CLVMNACSCAB1GQDE", "br": "NGDPRSAXDCBRQ", "mx": "NGDPRSAXDCMXQ",
}


def _fred_csv_to_quarterly(path: Path, col: str) -> pd.DataFrame:
    """Lee un CSV de FRED (date,value) y promedia a trimestre. Sirve para series
    mensuales o diarias; las trimestrales pasan sin cambio (un dato por trimestre)."""
    d = pd.read_csv(path)
    d.columns = ["date", col]
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d[col] = pd.to_numeric(d[col], errors="coerce")
    d = d.dropna()
    d["period"] = d["date"].dt.year.astype(str) + "Q" + d["date"].dt.quarter.astype(str)
    return d.groupby("period")[col].mean().reset_index()


def build_commodity_index(fred_dir: Path) -> pd.DataFrame:
    """Construye el indice de commodities trimestral ponderado por canasta."""
    parts = [_fred_csv_to_quarterly(fred_dir / f"{sid}.csv", name)
             for name, sid in COMMODITY_FILES.items()]
    com = parts[0]
    for p in parts[1:]:
        com = com.merge(p, on="period", how="inner")
    ws = sum(COMMODITY_WEIGHTS.values())
    com["commodity_idx"] = np.exp(sum((COMMODITY_WEIGHTS[k] / ws) * np.log(com[k]) for k in COMMODITY_WEIGHTS))
    com["_y"] = com["period"].str[:4].astype(int)
    com["_q"] = com["period"].str[-1].astype(int)
    com = com.sort_values(["_y", "_q"]).reset_index(drop=True)
    com = com.rename(columns={"oil": "brent"})
    return com[["period", "brent", "coal", "coffee", "nickel", "metal", "commodity_idx"]]


def build_foreign_demand(fred_dir: Path) -> pd.DataFrame:
    """Indice de demanda externa: PIB de socios en indice base 100, ponderado."""
    parts = [_fred_csv_to_quarterly(fred_dir / f"{sid}.csv", name)
             for name, sid in PARTNER_FILES.items()]
    fd = parts[0]
    for p in parts[1:]:
        fd = fd.merge(p, on="period", how="inner")
    fd["_y"] = fd["period"].str[:4].astype(int)
    fd["_q"] = fd["period"].str[-1].astype(int)
    fd = fd.sort_values(["_y", "_q"]).reset_index(drop=True)
    ws = sum(PARTNER_WEIGHTS.values())
    for k in PARTNER_WEIGHTS:
        fd[k + "_i"] = fd[k] / fd[k].iloc[0] * 100.0
    fd["foreign_demand_idx"] = np.exp(sum((PARTNER_WEIGHTS[k] / ws) * np.log(fd[k + "_i"]) for k in PARTNER_WEIGHTS))
    return fd[["period", "foreign_demand_idx"]]


def main() -> None:
    import sys

    fred_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / ".fredtmp"
    if not fred_dir.exists():
        raise SystemExit(
            f"No existe {fred_dir}. Descarga primero los CSV de FRED con curl "
            "(ver el docstring de este modulo)."
        )
    com = build_commodity_index(fred_dir)
    com.to_csv(OUT_COMMODITIES, index=False)
    print(f"commodities_quarterly.csv: {len(com)} filas ({com['period'].iloc[0]} - {com['period'].iloc[-1]})")
    fd = build_foreign_demand(fred_dir)
    fd.to_csv(OUT_FOREIGN, index=False)
    print(f"foreign_demand_quarterly.csv: {len(fd)} filas ({fd['period'].iloc[0]} - {fd['period'].iloc[-1]})")


if __name__ == "__main__":
    main()
