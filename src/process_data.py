from __future__ import annotations

import io
import re
from pathlib import Path

import pandas as pd

from mf_model import DEFAULT_PARAMETERS, MOBILITY_OPTIONS, SCENARIO_MECHANISMS, scenario_table, validate_signs


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data_raw"
OUT = ROOT / "data_processed"
DOCS = ROOT / "docs"
OUTPUTS = ROOT / "outputs"


ROW_MAP = {
    "domestic_demand": 12,
    "total_consumption": 13,
    "private_consumption": 14,
    "government_consumption": 15,
    "investment": 16,
    "fixed_investment": 17,
    "exports": 18,
    "imports": 19,
    "gdp": 20,
}


def _to_float(value):
    if pd.isna(value):
        return None
    return float(value)


def parse_dane_gdp(path: Path, prefix: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="Cuadro 1", header=None)
    rows = []
    year = None
    for col in range(2, df.shape[1]):
        year_cell = df.iat[9, col]
        quarter_cell = df.iat[10, col]
        if pd.notna(year_cell):
            match = re.search(r"\d{4}", str(year_cell))
            if match:
                year = int(match.group(0))
        if year is None or pd.isna(quarter_cell):
            continue
        quarter_text = str(quarter_cell).strip().upper()
        quarter = {"I": 1, "II": 2, "III": 3, "IV": 4}.get(quarter_text)
        if quarter is None:
            continue
        record = {"period": f"{year}Q{quarter}", "year": year, "quarter": quarter}
        for name, row in ROW_MAP.items():
            record[f"{name}_{prefix}_cop_billion"] = _to_float(df.iat[row, col])
        rows.append(record)
    return pd.DataFrame(rows)


def parse_trm(path: Path) -> tuple[pd.DataFrame, dict]:
    trm = pd.read_csv(path)
    trm["date"] = pd.to_datetime(trm["vigenciadesde"]).dt.tz_localize(None)
    trm = trm.rename(columns={"valor": "trm_cop_per_usd"})
    trm = trm[["date", "trm_cop_per_usd", "unidad", "vigenciahasta"]].sort_values("date")
    trm_q = (
        trm.set_index("date")["trm_cop_per_usd"]
        .resample("QE")
        .agg(["mean", "last"])
        .rename(columns={"mean": "trm_avg_cop_per_usd", "last": "trm_end_cop_per_usd"})
        .reset_index()
    )
    trm_q["period"] = trm_q["date"].dt.to_period("Q").astype(str).str.replace("Q", "Q")
    latest = trm.iloc[-1].to_dict()
    latest["trm_latest_date"] = str(latest.pop("date").date())
    return trm_q, latest


def parse_ipc(path: Path, year: int = 2026) -> dict:
    """Extrae inflacion del anexo IPC del DANE para el anio indicado.

    El anexo trae una fila por anio en la columna 0. Si el archivo cambia de
    estructura o no contiene el anio buscado, lanza ValueError explicito en vez
    de un IndexError opaco (el Excel del DANE se renombra/reestructura cada anio).
    """
    df = pd.read_excel(path, sheet_name="1", header=None)
    matches = df[df[0] == year]
    if matches.empty:
        anios_disponibles = sorted(
            int(v) for v in df[0].dropna().unique()
            if isinstance(v, (int, float)) and 1990 <= v <= 2100
        )
        raise ValueError(
            f"parse_ipc: no hay fila para el anio {year} en {path.name}. "
            f"Anios disponibles: {anios_disponibles}. "
            "Probablemente el Excel del DANE cambio de estructura; ajusta el parametro 'year'."
        )
    row = matches.iloc[0]
    return {
        "inflation_reference_date": f"{year}-03",
        "inflation_monthly_pct": float(row[1]),
        "inflation_ytd_pct": float(row[2]),
        "inflation_yoy_pct": float(row[3]),
    }


def parse_fed_h15(path: Path) -> dict:
    # The Fed H.15 page is the official current release. If table parsing changes,
    # use the published latest value observed on 2026-04-22.
    fallback = {"foreign_rate_reference_date": "2026-04-22", "foreign_rate_pct": 3.64}
    if not path.exists():
        return fallback
    html = path.read_text(encoding="utf-8", errors="ignore")
    row_match = re.search(r"Federal funds \(effective\).*?</tr>", html, flags=re.IGNORECASE | re.DOTALL)
    if row_match:
        values = re.findall(r">\s*&nbsp;?([0-9]+\.[0-9]+)&nbsp;?\s*<", row_match.group(0))
        if values:
            return {"foreign_rate_reference_date": "2026-04-22", "foreign_rate_pct": float(values[-1])}
    try:
        tables = pd.read_html(io.StringIO(html))
    except ValueError:
        return fallback
    for table in tables:
        text = table.astype(str).to_string()
        if "Federal funds" not in text:
            continue
        values = re.findall(r"\b\d+\.\d+\b", text)
        if values:
            return {"foreign_rate_reference_date": "2026-04-22", "foreign_rate_pct": float(values[-1])}
    return fallback


# Snapshot values from Banco de la Republica - Informe de Balanza de Pagos IV-2025.
# Source: https://www.banrep.gov.co/es/publicaciones-investigaciones/informe-balanza-pagos/cuarto-trimestre-2025
# Captured: 2026-04-24. Update when next BoP report is published.
BANREP_BOP_SNAPSHOT_2025Q4: dict[str, float] = {
    "policy_rate_pct_fallback": 11.25,                  # Tasa de politica BanRep
    "current_account_usd_m": -3912.0,                   # CA trimestral
    "current_account_pct_gdp": -3.1,                    # CA / PIB trimestral
    "financial_account_inflow_usd_m": 3471.0,           # KA trimestral neto
    "financial_account_pct_gdp": 2.7,                   # KA / PIB trimestral
    "errors_omissions_usd_m": 441.0,                    # Errores y omisiones
    "trade_services_balance_usd_m": -4457.0,            # Balanza bienes + servicios
    "factor_income_balance_usd_m": -3680.0,             # Renta de los factores
    "current_transfers_usd_m": 4224.0,                  # Transferencias corrientes
}


def parse_banrep_bop(path: Path) -> dict:
    """Extrae la tasa de politica del HTML del BanRep y combina con snapshot
    estatico de la balanza de pagos IV-2025.

    Solo la tasa de politica se intenta extraer del HTML (es robusto con regex).
    El resto vienen del snapshot ``BANREP_BOP_SNAPSHOT_2025Q4`` que se captura
    manualmente del informe trimestral. Refrescar cuando salga el siguiente
    informe.
    """
    text = path.read_text(encoding="utf-8", errors="ignore")
    clean = re.sub(r"&nbsp;|\s+", " ", text)
    policy_match = re.search(r"Tasa actual:\s*([0-9]+,[0-9]+)%", clean)
    snap = BANREP_BOP_SNAPSHOT_2025Q4
    return {
        "policy_rate_pct": float(policy_match.group(1).replace(",", ".")) if policy_match else snap["policy_rate_pct_fallback"],
        "policy_rate_reference_date": "2026-04-01",
        "current_account_usd_m": snap["current_account_usd_m"],
        "current_account_pct_gdp": snap["current_account_pct_gdp"],
        "financial_account_inflow_usd_m": snap["financial_account_inflow_usd_m"],
        "financial_account_pct_gdp": snap["financial_account_pct_gdp"],
        "errors_omissions_usd_m": snap["errors_omissions_usd_m"],
        "trade_services_balance_usd_m": snap["trade_services_balance_usd_m"],
        "factor_income_balance_usd_m": snap["factor_income_balance_usd_m"],
        "current_transfers_usd_m": snap["current_transfers_usd_m"],
        "bop_reference_period": "2025Q4",
        "gdp_bp_reference_usd_m": snap["current_account_usd_m"] / snap["current_account_pct_gdp"] * 100.0,
    }


def build_calibration() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    OUT.mkdir(parents=True, exist_ok=True)
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)

    real = parse_dane_gdp(RAW / "dane_pib_gasto_constantes_ivtrim2025.xlsx", "real")
    nominal = parse_dane_gdp(RAW / "dane_pib_gasto_corriente_ivtrim2025.xlsx", "nominal")
    quarterly = pd.merge(real, nominal, on=["period", "year", "quarter"], how="inner")

    trm_q, trm_latest = parse_trm(RAW / "trm_datos_abiertos.csv")
    quarterly = quarterly.merge(trm_q[["period", "trm_avg_cop_per_usd", "trm_end_cop_per_usd"]], on="period", how="left")
    quarterly["net_exports_real_cop_billion"] = quarterly["exports_real_cop_billion"] - quarterly["imports_real_cop_billion"]
    quarterly["net_exports_nominal_cop_billion"] = quarterly["exports_nominal_cop_billion"] - quarterly["imports_nominal_cop_billion"]
    quarterly["gdp_usd_m"] = quarterly["gdp_nominal_cop_billion"] * 1000.0 / quarterly["trm_avg_cop_per_usd"]

    latest_q = quarterly[quarterly["period"] == "2025Q4"].iloc[0].to_dict()
    ipc = parse_ipc(RAW / "dane_ipc_mar2026.xlsx")
    fed = parse_fed_h15(RAW / "federalreserve_h15.html")
    bop = parse_banrep_bop(RAW / "banrep_bop_iv_2025.html")

    calibration = {
        "calibration_date": "2026-04-24",
        "gdp_data_period": "2025Q4",
        "gdp_real_cop_billion": latest_q["gdp_real_cop_billion"],
        "gdp_nominal_cop_billion": latest_q["gdp_nominal_cop_billion"],
        "private_consumption_real_cop_billion": latest_q["private_consumption_real_cop_billion"],
        "private_consumption_nominal_cop_billion": latest_q["private_consumption_nominal_cop_billion"],
        "government_consumption_real_cop_billion": latest_q["government_consumption_real_cop_billion"],
        "government_consumption_nominal_cop_billion": latest_q["government_consumption_nominal_cop_billion"],
        "investment_real_cop_billion": latest_q["investment_real_cop_billion"],
        "investment_nominal_cop_billion": latest_q["investment_nominal_cop_billion"],
        "exports_real_cop_billion": latest_q["exports_real_cop_billion"],
        "exports_nominal_cop_billion": latest_q["exports_nominal_cop_billion"],
        "imports_real_cop_billion": latest_q["imports_real_cop_billion"],
        "imports_nominal_cop_billion": latest_q["imports_nominal_cop_billion"],
        "net_exports_real_cop_billion": latest_q["net_exports_real_cop_billion"],
        "net_exports_nominal_cop_billion": latest_q["net_exports_nominal_cop_billion"],
        "trm_cop_per_usd": float(trm_latest["trm_cop_per_usd"]),
        "trm_latest_date": trm_latest["trm_latest_date"],
        "trm_q4_2025_avg_cop_per_usd": latest_q["trm_avg_cop_per_usd"],
        "real_exchange_rate_index": 100.0,
        "money_supply_m3_cop_billion": 997204.12,
        "money_supply_reference_date": "2026-03",
        "reserves_usd_m": 66611.0,
        "reserves_reference_date": "2026-03",
        "risk_premium_pct": 8.41,
        "risk_premium_reference_date": "2026-04-15",
        # Promedio trimestral 2026Q2 de la serie Brent del propio repo
        # (commodities_quarterly.csv, FRED DCOILBRENTEU). El badge en vivo lo
        # sobrescribe con el dato diario de FRED cuando hay red.
        "oil_brent_usd_per_barrel": 104.55,
        "oil_reference_date": "2026-Q2 (prom., FRED DCOILBRENTEU)",
        "terms_of_trade_index": 125.64,
        "terms_of_trade_reference_date": "2026-01",
        "fiscal_deficit_gnc_cop_billion": -117807.0,
        "fiscal_deficit_gnc_pct_gdp": -6.4,
        "primary_deficit_gnc_cop_billion": -65700.0,
        "gross_debt_gnc_pct_gdp": 64.4,
        **ipc,
        **fed,
        **bop,
    }

    calib_long = pd.DataFrame(
        [{"variable": k, "value": v, "classification": _classify_variable(k)} for k, v in calibration.items()]
    )
    params = pd.DataFrame(
        [
            {
                "parameter": k,
                "value": v,
                "classification": "supuesto calibrable",
                "note": _parameter_note(k),
            }
            for k, v in DEFAULT_PARAMETERS.items()
        ]
    )

    quarterly.to_csv(OUT / "quarterly_master.csv", index=False)
    calib_long.to_csv(OUT / "base_calibration.csv", index=False)
    params.to_csv(OUT / "parameters.csv", index=False)

    source_matrix().to_csv(OUT / "source_matrix.csv", index=False)
    data_dictionary().to_csv(OUT / "data_dictionary.csv", index=False)

    scenarios_both = pd.concat(
        [scenario_table(calibration, mobility=m) for m in MOBILITY_OPTIONS],
        ignore_index=True,
    )
    scenarios_both.to_csv(OUTPUTS / "scenario_results.csv", index=False)
    tests_both = pd.concat(
        [validate_signs(calibration, mobility=m) for m in MOBILITY_OPTIONS],
        ignore_index=True,
    )
    tests_both.to_csv(OUTPUTS / "validation_tests.csv", index=False)
    scenario_docs().to_csv(OUTPUTS / "scenario_mechanisms.csv", index=False)

    return quarterly, calib_long, params


def _classify_variable(name: str) -> str:
    if any(x in name for x in ["reference_date", "period", "calibration_date"]):
        return "metadato"
    if name in {"risk_premium_pct", "oil_brent_usd_per_barrel", "terms_of_trade_index", "money_supply_m3_cop_billion", "reserves_usd_m"}:
        return "observada via proxy publico"
    if "gdp_bp_reference" in name or "real_exchange_rate_index" in name:
        return "transformada"
    if "fiscal" in name or "debt" in name or "primary" in name:
        return "observada resumen oficial"
    return "observada"


def _parameter_note(name: str) -> str:
    notes = {
        "mpc": "Propension marginal a consumir dentro de rangos usuales para modelos macro simples.",
        "investment_rate_sensitivity": "Caida porcentual de la inversion por punto porcentual de aumento de la tasa real.",
        "money_rate_sensitivity": "Cambio en tasa domestica, en pp, ante 1% de choque a M3.",
        "capital_flow_sensitivity_usd_m_per_pp": "Sensibilidad de entradas netas de capital al diferencial de tasas ajustado por riesgo.",
        "exchange_rate_bp_sensitivity": "Ajuste de la TRM ante brecha de balanza de pagos como proporcion del PIB trimestral en USD.",
    }
    return notes.get(name, "Parametro conductual supuesto y editable en la app.")


def source_matrix() -> pd.DataFrame:
    rows = [
        ["PIB y componentes gasto reales", "DANE", "https://www.dane.gov.co/files/operaciones/PIB/anex-GastoConstantes-IVtrim2025.xlsx", "Trimestral", "2025Q4", "XLSX", "Alta", "Descargado."],
        ["PIB y componentes gasto corrientes", "DANE", "https://www.dane.gov.co/files/operaciones/PIB/anex-GastoCorriente-IVtrim2025.xlsx", "Trimestral", "2025Q4", "XLSX", "Alta", "Descargado."],
        ["TRM diaria", "Datos Abiertos / Superfinanciera", "https://www.datos.gov.co/resource/32sa-8pi3.csv", "Diaria", "2026-04-24", "Socrata CSV", "Alta", "Descargado."],
        ["IPC e inflacion", "DANE", "https://www.dane.gov.co/files/operaciones/IPC/mar2026/anex-IPC-mar2026.xlsx", "Mensual", "2026-03", "XLSX", "Alta", "Descargado."],
        ["Tasa de politica monetaria", "Banco de la Republica", "https://www.banrep.gov.co/es/publicaciones-investigaciones/informe-balanza-pagos/cuarto-trimestre-2025", "Evento", "2026-04-01", "HTML", "Alta", "Extraida de pagina BanRep."],
        ["Cuenta corriente y financiera", "Banco de la Republica", "https://www.banrep.gov.co/es/publicaciones-investigaciones/informe-balanza-pagos/cuarto-trimestre-2025", "Trimestral", "2025Q4", "HTML", "Alta", "Extraida de informe."],
        ["Tasa externa", "Federal Reserve H.15", "https://www.federalreserve.gov/releases/h15/", "Diaria", "2026-04-22", "HTML", "Alta", "Descargado."],
        ["Balance fiscal GNC", "MHCP / BanRep informe Congreso", "https://www.minhacienda.gov.co/politica-fiscal/cifras-de-politica-fiscal/gobierno-nacional-central/balance/-/document_library/dgai/view_file/2107913", "Anual", "2025", "XLSX/HTML", "Alta", "El XLSX activa bloqueo anti-bot; cifras base tomadas del resumen publico BanRep/MHCP."],
        ["M3", "BanRep via Trading Economics", "https://tradingeconomics.com/colombia/money-supply-m3", "Mensual", "2026-03", "HTML proxy", "Media", "Proxy publico que cita Banco de la Republica."],
        ["Reservas internacionales", "BanRep via Trading Economics", "https://tradingeconomics.com/colombia/money-supply-m3", "Mensual", "2026-03", "HTML proxy", "Media", "Proxy publico que cita Banco de la Republica."],
        ["Precio Brent", "FRED/EIA y CountryEconomy", "https://fred.stlouisfed.org/series/DCOILBRENTEU", "Diaria", "2026-04-22", "HTML proxy", "Media", "FRED no resolvio DNS en shell; valor mas reciente tomado de proxy publico."],
        ["Prima de riesgo", "CountryEconomy", "https://countryeconomy.com/risk-premium/colombia", "Diaria", "2026-04-15", "HTML proxy", "Media", "Proxy de riesgo pais vs bonos de EE. UU.; editable en app."],
        ["Terminos de intercambio", "BanRep via Trading Economics", "https://es.tradingeconomics.com/colombia/terms-of-trade", "Mensual", "2026-01", "HTML proxy", "Media", "Proxy publico; BanRep documenta metodologia ITI."],
    ]
    return pd.DataFrame(
        rows,
        columns=["Variable requerida", "Fuente elegida", "URL exacta", "Frecuencia", "Ultima fecha disponible", "Archivo/API", "Confiabilidad", "Comentario"],
    )


def data_dictionary() -> pd.DataFrame:
    rows = [
        ["gdp_real_cop_billion", "PIB real trimestral", "COP miles de millones, precios 2015", "Trimestral", "DANE", "Observada"],
        ["gdp_nominal_cop_billion", "PIB nominal trimestral", "COP miles de millones", "Trimestral", "DANE", "Observada"],
        ["private_consumption_real_cop_billion", "Consumo privado real", "COP miles de millones, precios 2015", "Trimestral", "DANE", "Observada"],
        ["government_consumption_real_cop_billion", "Consumo publico real", "COP miles de millones, precios 2015", "Trimestral", "DANE", "Observada"],
        ["investment_real_cop_billion", "Formacion bruta de capital real", "COP miles de millones, precios 2015", "Trimestral", "DANE", "Observada"],
        ["exports_real_cop_billion", "Exportaciones reales", "COP miles de millones, precios 2015", "Trimestral", "DANE", "Observada"],
        ["imports_real_cop_billion", "Importaciones reales", "COP miles de millones, precios 2015", "Trimestral", "DANE", "Observada"],
        ["trm_cop_per_usd", "TRM vigente", "COP/USD", "Diaria", "Datos Abiertos/SFC", "Observada"],
        ["policy_rate_pct", "Tasa de politica monetaria", "Porcentaje efectivo anual", "Evento", "BanRep", "Observada"],
        ["current_account_usd_m", "Cuenta corriente", "USD millones", "Trimestral", "BanRep", "Observada"],
        ["financial_account_inflow_usd_m", "Entradas netas de capital", "USD millones", "Trimestral", "BanRep", "Observada"],
        ["money_supply_m3_cop_billion", "Agregado monetario M3", "COP miles de millones", "Mensual", "BanRep/proxy", "Observada via proxy"],
        ["oil_brent_usd_per_barrel", "Precio Brent", "USD/barril", "Diaria", "EIA/FRED/proxy", "Observada via proxy"],
        ["risk_premium_pct", "Prima de riesgo Colombia", "Porcentaje", "Diaria", "CountryEconomy", "Proxy"],
    ]
    return pd.DataFrame(rows, columns=["variable", "descripcion", "unidad", "frecuencia_final", "fuente", "clasificacion"])


def scenario_docs() -> pd.DataFrame:
    return pd.DataFrame([{"scenario": k, "mechanism": v} for k, v in SCENARIO_MECHANISMS.items()])


def main() -> None:
    quarterly, calibration, params = build_calibration()
    print(f"Quarterly rows: {len(quarterly)}")
    print(f"Calibration variables: {len(calibration)}")
    print(f"Parameters: {len(params)}")
    print("Outputs written to", OUT)


if __name__ == "__main__":
    main()
