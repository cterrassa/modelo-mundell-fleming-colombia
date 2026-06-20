"""Pruebas de signos canonicos del modelo, corriendo validate_signs en pytest.

Antes, los 22 chequeos de signo solo se serializaban a outputs/validation_tests.csv
desde process_data.py; ningun test los ejecutaba como asercion (TEST-01). Si un
refactor rompia un signo canonico (p.ej. expansion fiscal deja de apreciar en
perfecta) pytest seguia verde. Este modulo cierra esa brecha en los 3 regimenes.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mf_model import MOBILITY_OPTIONS, validate_signs


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


@pytest.mark.parametrize("mobility", MOBILITY_OPTIONS)
def test_all_sign_checks_pass(calibration, mobility):
    """Todos los chequeos de signo deben pasar en cada regimen."""
    df = validate_signs(calibration, mobility=mobility)
    failed = df[~df["passed"]]
    assert failed.empty, (
        f"Signos rotos en regimen '{mobility}':\n"
        f"{failed[['test', 'metric', 'value', 'condition']].to_string(index=False)}"
    )


def test_sign_check_count(calibration):
    """Conteo esperado por regimen (9 perfecta + 8 imperfecta + 5 fijo = 22)."""
    counts = {m: len(validate_signs(calibration, mobility=m)) for m in MOBILITY_OPTIONS}
    assert counts == {"perfecta": 9, "imperfecta": 8, "fijo": 5}, counts


def test_committed_csv_covers_all_regimes():
    """outputs/validation_tests.csv (regenerado por el ETL) cubre los 3 regimenes."""
    df = pd.read_csv(ROOT / "outputs" / "validation_tests.csv")
    assert set(df["mobility"].unique()) == set(MOBILITY_OPTIONS)
    assert bool(df["passed"].all())
