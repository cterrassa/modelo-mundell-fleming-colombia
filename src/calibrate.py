"""Calibracion OLS de las elasticidades comerciales del modelo MF.

Estima desde quarterly_master.csv (2005-2025, 84 trimestres) los parametros:
- eta_import_y : elasticidad ingreso de las importaciones reales.
- eta_import_q : elasticidad (en valor absoluto) de M reales al tipo de cambio.
- eta_export_q : elasticidad de X reales al tipo de cambio.

Metodologia:
- Diferencias logaritmicas interanuales (Delta_4 ln) para remover estacionalidad
  y evitar regresion espuria sobre series no estacionarias en niveles.
- Tipo de cambio real proxy: TRM nominal deflactada por el deflactor del PIB
  (gdp_nominal/gdp_real). Sin precios externos, el factor foraneo se absorbe en
  la tendencia y se diferencia; en variaciones esto es defendible.
- OLS con errores estandar clasicos calculados con numpy (sin statsmodels para
  no re-agregar la dependencia al deploy). Este script es offline: su salida se
  cablea a parameters.csv.

Limitaciones declaradas:
- output_rate_sensitivity NO se estima aqui: requiere serie de tasa de interes
  real trimestral que no esta en el panel. Se mantiene el valor tipo Taylor.
- La elasticidad de exportaciones omite demanda externa (PIB socios): las
  exportaciones colombianas son intensivas en commodities, asi que el coef.
  de TRM puede salir pequeno. Se reporta con esa advertencia.
- Endogeneidad de la TRM no se corrige con IV (seria sobre-ingenieria para una
  calibracion): los coeficientes son asociaciones condicionales, no causales
  estrictos.

Run: python src/calibrate.py
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data_processed" / "quarterly_master.csv"
YOY_LAG = 4  # trimestres para la diferencia interanual


def _ols(y: np.ndarray, X: np.ndarray) -> dict:
    """OLS con errores estandar clasicos. X debe incluir la constante.

    Devuelve coeficientes, errores estandar, t-stats, R2 y n.
    """
    n, k = X.shape
    xtx_inv = np.linalg.inv(X.T @ X)
    beta = xtx_inv @ X.T @ y
    resid = y - X @ beta
    dof = n - k
    sigma2 = float(resid.T @ resid) / dof
    var_beta = sigma2 * xtx_inv
    se = np.sqrt(np.diag(var_beta))
    ss_tot = float(((y - y.mean()) ** 2).sum())
    ss_res = float((resid ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return {
        "beta": beta,
        "se": se,
        "t": beta / se,
        "r2": r2,
        "n": n,
        "dof": dof,
    }


def _yoy_dln(series: pd.Series) -> pd.Series:
    """Diferencia logaritmica interanual: ln(x_t) - ln(x_{t-4})."""
    return np.log(series) - np.log(series.shift(YOY_LAG))


def estimate() -> dict:
    df = pd.read_csv(PANEL).sort_values("period").reset_index(drop=True)

    # Deflactor del PIB (base = primer valor), TRM real proxy.
    deflator = df["gdp_nominal_cop_billion"] / df["gdp_real_cop_billion"]
    trm_real = df["trm_avg_cop_per_usd"] / deflator

    dln_m = _yoy_dln(df["imports_real_cop_billion"])
    dln_x = _yoy_dln(df["exports_real_cop_billion"])
    dln_y = _yoy_dln(df["gdp_real_cop_billion"])
    dln_trm_real = _yoy_dln(trm_real)
    dln_trm_nom = _yoy_dln(df["trm_avg_cop_per_usd"])

    base = pd.DataFrame({
        "dln_m": dln_m, "dln_x": dln_x, "dln_y": dln_y,
        "dln_trm_real": dln_trm_real, "dln_trm_nom": dln_trm_nom,
    }).dropna().reset_index(drop=True)

    results: dict = {"n_obs": len(base)}

    # --- 1. Demanda de importaciones: dln_m ~ dln_y + dln_trm_real ---
    X_imp = np.column_stack([np.ones(len(base)), base["dln_y"], base["dln_trm_real"]])
    imp = _ols(base["dln_m"].to_numpy(), X_imp)
    eta_import_y = float(imp["beta"][1])
    eta_import_q = float(-imp["beta"][2])  # modelo define eta_import_q positivo; TRM sube -> M baja
    results["import_demand"] = {
        "eta_import_y": eta_import_y,
        "eta_import_y_se": float(imp["se"][1]),
        "eta_import_q": eta_import_q,
        "eta_import_q_se": float(imp["se"][2]),
        "r2": imp["r2"], "n": imp["n"],
    }

    # --- 2. Demanda de exportaciones: dln_x ~ dln_trm_real (omite demanda externa) ---
    X_exp = np.column_stack([np.ones(len(base)), base["dln_trm_real"]])
    exp = _ols(base["dln_x"].to_numpy(), X_exp)
    eta_export_q = float(exp["beta"][1])
    results["export_demand"] = {
        "eta_export_q": eta_export_q,
        "eta_export_q_se": float(exp["se"][1]),
        "r2": exp["r2"], "n": exp["n"],
    }

    # --- 3. Robustez: misma con TRM nominal ---
    X_imp_n = np.column_stack([np.ones(len(base)), base["dln_y"], base["dln_trm_nom"]])
    imp_n = _ols(base["dln_m"].to_numpy(), X_imp_n)
    X_exp_n = np.column_stack([np.ones(len(base)), base["dln_trm_nom"]])
    exp_n = _ols(base["dln_x"].to_numpy(), X_exp_n)
    results["robustness_nominal_trm"] = {
        "eta_import_y": float(imp_n["beta"][1]),
        "eta_import_q": float(-imp_n["beta"][2]),
        "eta_export_q": float(exp_n["beta"][1]),
    }

    return results


def _fmt(v: float) -> str:
    return f"{v:+.4f}"


def main() -> None:
    r = estimate()
    print(f"Calibracion OLS sobre quarterly_master.csv (YoY log-diff, n={r['n_obs']})")
    print("=" * 70)
    imp = r["import_demand"]
    print("\n[1] Demanda de importaciones: dln(M) ~ dln(Y) + dln(TRM_real)")
    print(f"    eta_import_y = {_fmt(imp['eta_import_y'])}  (SE {imp['eta_import_y_se']:.4f})")
    print(f"    eta_import_q = {_fmt(imp['eta_import_q'])}  (SE {imp['eta_import_q_se']:.4f})")
    print(f"    R2 = {imp['r2']:.3f}, n = {imp['n']}")
    exp = r["export_demand"]
    print("\n[2] Demanda de exportaciones: dln(X) ~ dln(TRM_real)  [omite demanda externa]")
    print(f"    eta_export_q = {_fmt(exp['eta_export_q'])}  (SE {exp['eta_export_q_se']:.4f})")
    print(f"    R2 = {exp['r2']:.3f}, n = {exp['n']}")
    rob = r["robustness_nominal_trm"]
    print("\n[3] Robustez con TRM nominal:")
    print(f"    eta_import_y = {_fmt(rob['eta_import_y'])}, eta_import_q = {_fmt(rob['eta_import_q'])}, eta_export_q = {_fmt(rob['eta_export_q'])}")
    print("\nComparacion con calibracion actual (parameters.csv):")
    print("    eta_import_y: 1.35 (actual)")
    print("    eta_import_q: 0.25 (actual)")
    print("    eta_export_q: 0.45 (actual)")


if __name__ == "__main__":
    main()
