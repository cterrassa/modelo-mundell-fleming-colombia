# Modelo Mundell-Fleming Colombia

Simulador interactivo del modelo Mundell-Fleming aplicado al caso colombiano,
desplegado como app Streamlit. Material academico para la Maestria en Economia
Aplicada de UniAndes (curso de Macroeconomia, presentaciones 34-39).

App publica: https://modelo-mundell-fleming-colombia.onrender.com/

## Que ofrece

- **Modo dual de movilidad de capitales:**
  - **Perfecta** (canonico Mankiw cap. 13): tasa anclada por UIP, politica fiscal
    no mueve el producto, politica monetaria efectiva. Resolucion en forma cerrada.
  - **Imperfecta** (calibracion empirica para Colombia): BP con pendiente positiva,
    ajuste de TRM via residual de balanza de pagos, regla de Taylor para Banrep.
- **8 sliders de choques** alineados a Mankiw + Banrep: G, T, M, tasa Banrep, tasa
  Fed, prima de riesgo Colombia, Brent, NX autonomo.
- **Datos en vivo** (TRM Datos Abiertos, Fed funds y Brent FRED) con cache 1 h y
  fallback transparente a snapshot.
- **Proyeccion deterministica a 5 anios** bajo escenarios predefinidos. Sin Monte
  Carlo, fiel a la logica del modelo.
- **Tabla consolidada de cuentas nacionales + proyecciones** con descarga CSV.
- **Backtesting** trimestre a trimestre contra TRM observada (RMSE, MAE,
  correlacion).
- **Diagrama IS-LM-BP** con curvas que se redibujan en vivo.

## Estructura

```text
app/
  app.py                Streamlit principal
src/
  mf_model.py           simulate(), perfecta + imperfecta, validate_signs
  mf_curves.py          helpers para dibujar IS, LM, BP en plano (gap, rate)
  mf_projection.py      project() determinista a 5 anios + escenarios
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

```bash
PYTHONPATH=src python -c "import mf_model, pandas as pd; calib_df = pd.read_csv('data_processed/base_calibration.csv'); calib = {r['variable']: float(r['value']) if str(r['value']).replace('.','').replace('-','').isdigit() else r['value'] for _,r in calib_df.iterrows()}; print(mf_model.validate_signs(calib, mobility='perfecta')); print(mf_model.validate_signs(calib, mobility='imperfecta'))"
```

Las 17 pruebas de signos deben pasar.

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

Material academico de uso educativo. Modelo y ecuaciones tomados de Mankiw
(8a/9a ed.) y de las presentaciones del curso de Macroeconomia, UniAndes
MECA.
