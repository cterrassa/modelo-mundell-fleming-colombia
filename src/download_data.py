from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data_raw"


URLS = {
    "dane_pib_gasto_constantes_ivtrim2025.xlsx": "https://www.dane.gov.co/files/operaciones/PIB/anex-GastoConstantes-IVtrim2025.xlsx",
    "dane_pib_gasto_corriente_ivtrim2025.xlsx": "https://www.dane.gov.co/files/operaciones/PIB/anex-GastoCorriente-IVtrim2025.xlsx",
    "dane_ipc_mar2026.xlsx": "https://www.dane.gov.co/files/operaciones/IPC/mar2026/anex-IPC-mar2026.xlsx",
    "trm_datos_abiertos.csv": "https://www.datos.gov.co/resource/32sa-8pi3.csv?%24limit=100000&%24order=vigenciadesde",
    "federalreserve_h15.html": "https://www.federalreserve.gov/releases/h15/",
    "banrep_bop_iv_2025.html": "https://www.banrep.gov.co/es/publicaciones-investigaciones/informe-balanza-pagos/cuarto-trimestre-2025",
    "banrep_jdbr_congreso_marzo_2026.html": "https://www.banrep.gov.co/es/publicaciones-investigaciones/informe-junta-directiva-congreso/marzo-2026",
    "mhcp_balance_gnc_1994_2025.xlsx": "https://www.minhacienda.gov.co/documents/d/portal/balance-gnc-trimestral?download=true",
    "fred_brent.csv": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU",
    "fred_dxy_broad.csv": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTWEXBGS",
}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; MF-Colombia-Research/1.0)",
            "Accept": "*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read()


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    results = []
    for filename, url in URLS.items():
        path = RAW / filename
        try:
            data = fetch(url)
            path.write_bytes(data)
            status = "ok"
            detail = f"{len(data)} bytes"
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            status = "failed"
            detail = str(exc)
        results.append({"file": filename, "url": url, "status": status, "detail": detail})
        print(f"{status:6} {filename}: {detail}")

    (RAW / "download_log.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
