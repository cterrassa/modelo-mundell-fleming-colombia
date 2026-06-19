"""Tests de robustez: guards de E/S y validaciones de los modulos de datos.

Cubre los fixes del batch de blindaje (P30):
- backtest.run_backtest: panel de 1 fila lanza ValueError (no DataFrame vacio).
- backtest.aggregate_quarterly: valida columnas date/value.
- backtest: registra calculation_note ante division por cero.
- mf_projection._load_csv_path: valida year_offset presente y sin duplicados.
- imperfecta: comparativa estatica especifica del regimen.

Run: python -m pytest tests/ -v
"""

import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import backtest as bt
from mf_model import Shock, simulate
from mf_projection import _load_csv_path


@pytest.fixture(scope="module")
def calibration() -> dict:
    df = pd.read_csv(ROOT / "data_processed" / "base_calibration.csv")
    out: dict = {}
    for _, row in df.iterrows():
        try:
            out[row["variable"]] = float(row["value"])
        except (TypeError, ValueError):
            out[row["variable"]] = row["value"]
    return out


# ---------- backtest robustness ----------

def test_run_backtest_single_row_raises(calibration):
    """Panel de 1 fila debe lanzar ValueError, no devolver DataFrame vacio."""
    panel = pd.DataFrame({"quarter": ["2024Q1"], "trm": [3500.0]})
    with pytest.raises(ValueError, match="insuficiente"):
        bt.run_backtest(panel, calibration)


def test_run_backtest_empty_returns_empty(calibration):
    """Panel totalmente vacio devuelve DataFrame vacio (no error)."""
    result = bt.run_backtest(pd.DataFrame(), calibration)
    assert result.empty


def test_aggregate_quarterly_validates_columns():
    """aggregate_quarterly lanza ValueError si faltan columnas date/value."""
    bad = pd.DataFrame({"fecha": [1], "precio": [2]})
    with pytest.raises(ValueError, match="date"):
        bt.aggregate_quarterly(bad, "x")


def test_aggregate_quarterly_empty_ok():
    """DataFrame vacio devuelve estructura vacia con columnas correctas."""
    out = bt.aggregate_quarterly(pd.DataFrame(), "trm")
    assert list(out.columns) == ["quarter", "trm"]


def test_backtest_calculation_note_on_zero_trm(calibration):
    """Si prev_trm==0, la fila registra calculation_note='trm_prev=0'."""
    panel = pd.DataFrame({
        "quarter": ["2024Q1", "2024Q2", "2024Q3", "2024Q4"],
        "trm": [0.0, 3500.0, 3600.0, 3700.0],
    })
    out = bt.run_backtest(panel, calibration)
    assert "calculation_note" in out.columns
    # La primera transicion (i=1) usa prev_trm=0 -> nota registrada
    assert any("trm_prev=0" in str(n) for n in out["calculation_note"])


# ---------- _load_csv_path robustness ----------

def test_load_csv_missing_year_offset_raises():
    tmp = Path(tempfile.gettempdir()) / "mf_test_bad_noyear.csv"
    tmp.write_text("foo,bar\n1,2\n")
    try:
        with pytest.raises(ValueError, match="year_offset"):
            _load_csv_path(tmp)
    finally:
        tmp.unlink(missing_ok=True)


def test_load_csv_duplicate_year_offset_raises():
    tmp = Path(tempfile.gettempdir()) / "mf_test_bad_dup.csv"
    tmp.write_text("year_offset,government_spending_pct\n1,5\n1,6\n")
    try:
        with pytest.raises(ValueError, match="duplicad"):
            _load_csv_path(tmp)
    finally:
        tmp.unlink(missing_ok=True)


def test_load_csv_mfmp_proxy_valid():
    """El CSV proxy MFMP del repo carga y devuelve HORIZON_YEARS shocks."""
    from mf_projection import HORIZON_YEARS
    path = ROOT / "data_processed" / "mfmp_proxy_scenario.csv"
    shocks = _load_csv_path(path)
    assert len(shocks) == HORIZON_YEARS
    # El primer anio debe tener un choque fiscal no nulo (3.0 segun el CSV)
    assert shocks[0].government_spending_pct != 0.0


# ---------- imperfecta comparative statics ----------

def test_imperfecta_fiscal_moves_Y(calibration):
    """En imperfecta la politica fiscal SI mueve el producto."""
    base = simulate(calibration, Shock(), mobility="imperfecta")
    sim = simulate(calibration, Shock(government_spending_pct=5.0), mobility="imperfecta")
    assert sim["gdp_real_cop_billion"] > base["gdp_real_cop_billion"]


def test_imperfecta_domestic_rate_appreciates(calibration):
    """En imperfecta una subida de la tasa Banrep aprecia el peso (TRM baja)."""
    base = simulate(calibration, Shock(), mobility="imperfecta")
    sim = simulate(calibration, Shock(domestic_policy_rate_bp=100.0), mobility="imperfecta")
    assert sim["trm_cop_per_usd"] < base["trm_cop_per_usd"]


def test_perfecta_domestic_rate_no_effect(calibration):
    """En perfecta la tasa Banrep no tiene efecto (UIP la ancla)."""
    base = simulate(calibration, Shock(), mobility="perfecta")
    sim = simulate(calibration, Shock(domestic_policy_rate_bp=100.0), mobility="perfecta")
    assert abs(sim["trm_cop_per_usd"] - base["trm_cop_per_usd"]) < 1e-6
