# Modelo Mundell-Fleming Colombia

Simulador interactivo del modelo Mundell-Fleming aplicado al caso colombiano,
desplegado como app Streamlit.

App publica: https://modelo-mundell-fleming-colombia.onrender.com/

## Que ofrece

- **Tres regimenes (esquinas de la trinidad imposible):**
  - **Flexible + movilidad perfecta** (caso canonico): tasa anclada por UIP, politica fiscal
    no mueve el producto, politica monetaria efectiva. Resolucion en forma cerrada.
  - **Flexible + movilidad imperfecta** (calibracion empirica para Colombia): BP con pendiente positiva,
    ajuste de TRM via residual de balanza de pagos, regla de Taylor para Banrep.
  - **Tipo de cambio fijo**: TRM anclada, M endogena (defensa del peg);
    politica fiscal efectiva, politica monetaria autonoma inefectiva.
- **10 sliders de choques** que cubren los choques estandar del modelo y los relevantes para Colombia: a, h, G, T, M, tasa Banrep, tasa
  Fed, prima de riesgo Colombia, Brent, NX autonomo.
- **Datos en vivo** (TRM Datos Abiertos, Fed funds y Brent FRED) con cache 1 h y
  fallback transparente a snapshot.
- **Proyeccion deterministica a 5 anios** en dos modos: (a) **senda oficial del
  MHCP (MFMP 2026)** con las cifras publicadas (cuentas nacionales y TRM al
  quinquenio 2026-2030 o al mediano plazo 2026-2037), y (b) **proyeccion del
  modelo Mundell-Fleming** bajo escenarios de choques. Sin Monte Carlo.
- **Arbol de cuentas nacionales (MFMP):** descomposicion de la balanza de pagos
  (cuenta corriente, balanza comercial, servicios, renta factorial,
  transferencias, cuenta financiera) y del sector fiscal del GNC (ingreso, gasto,
  intereses, balance total y primario, deuda neta) para un anio elegido, con las
  identidades contables explicitas en % del PIB, billones COP y millones USD.
- **Tabla consolidada de cuentas nacionales + proyecciones** con descarga CSV.
- **Backtesting** trimestre a trimestre contra TRM observada (RMSE, MAE,
  correlacion).
- **Diagrama IS\*-LM\*** en plano (Y, TRM): IS\* con pendiente positiva, LM\* vertical, equilibrio en la interseccion. Las curvas se redibujan en vivo cuando cambias choque o modo.

## Estructura

```text
app/
  app.py                Streamlit principal
src/
  mf_model.py           simulate(), perfecta + imperfecta, validate_signs
  mf_curves.py          helpers para dibujar IS, LM, BP en plano (gap, rate)
  mf_projection.py      project() determinista a 5 anios + escenarios
  mfmp_official.py       senda oficial MFMP 2026 (MHCP) + arbol de cuentas nacionales
  consolidated_table.py historico DANE + proyeccion del modelo, anclado anual
  live_data.py          fetchers TRM (Datos Abiertos) + FRED (DFF, Brent)
  backtest.py           run_backtest() trimestre a trimestre, metricas RMSE/MAE
  download_data.py      ETL offline para regenerar el snapshot del repo
  process_data.py       parsea raw -> data_processed, escribe CSVs
data_raw/               Snapshots descargados (DANE, Banrep, Datos Abiertos)
data_processed/         CSVs limpios consumidos por la app
outputs/                scenario_results.csv, validation_tests.csv, charts
docs/
  metodologia.md        Modelo, datos, validacion, backtesting, limitaciones
```

## Ejecucion local

```bash
pip install -r requirements.txt
streamlit run app/app.py
```

O con el lanzador alternativo (usa `.deps/` si existe):

```bash
python run_app.py
```

## Regenerar el snapshot

Solo necesario si se quiere actualizar los CSVs del repo a una calibracion mas
reciente. La app ya consume datos en vivo de TRM, Fed funds y Brent en runtime.

```bash
python src/download_data.py   # descarga raw a data_raw/
python src/process_data.py    # parsea raw -> data_processed/
python src/make_charts.py     # graficos historicos en outputs/
```

## Despliegue

Render con `render.yaml` incluido. Auto-deploy desde `main` activado por
defecto. Si el webhook GitHub-Render se cae (ha pasado), usa **Manual Deploy
-> Deploy latest commit** en el dashboard.

Detalles en `DEPLOYMENT.md`.

## Tests

Suite completa (64 tests; incluye `tests/test_mfmp_official.py` que valida que las
identidades contables del MFMP cierran y que el CSV oficial es reproducible).
`tests/test_signs.py` ejecuta como aserciones pytest
los **22 chequeos de signo** (9 perfecta + 8 imperfecta + 5 fijo) sobre los 3
regimenes:

```bash
python -m pytest tests/ -q
```

Toda la suite debe pasar tras cualquier cambio al modelo.

Para el smoke test del Streamlit:

```python
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("app/app.py", default_timeout=60)
at.run()
assert len(at.exception) == 0
```

## Limitaciones importantes

Modelo estatico-comparativo y linealizado. NO pronostica TRM. Backtesting
solo incluye Fed funds y Brent como exogenos: no captura COVID 2020Q2,
paro 2021, ni inflacion 2022. La prima de riesgo entra al modelo via slider
pero no se backtestea por falta de serie publica fiable.

Detalles tecnicos completos en `docs/metodologia.md`.

## Licencia

Material de uso educativo. Modelo y ecuaciones siguen el desarrollo estandar
del modelo Mundell-Fleming para economia abierta pequena.
