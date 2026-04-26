# Modelo Mundell-Fleming Colombia

Proyecto reproducible para construir un modelo Mundell-Fleming de economia abierta pequena con tasa de cambio flexible, calibrado a la ultima informacion publica disponible para Colombia al 24 de abril de 2026.

## Estructura

```text
data_raw/        Archivos descargados desde DANE, BanRep, Datos Abiertos y otras fuentes.
data_processed/  Base trimestral, calibracion, parametros y matriz de fuentes.
src/             Descarga, procesamiento y modelo.
app/             App Streamlit con sliders.
outputs/         Resultados de escenarios y validacion economica.
docs/            Metodologia y notas de trazabilidad.
```

## Ejecucion

```bash
pip install -r requirements.txt
python src/download_data.py
python src/process_data.py
python src/make_charts.py
streamlit run app/app.py
```

En esta sesion deje tambien un lanzador local que usa las dependencias instaladas en `.deps`:

```bash
python run_app.py
```

## Despliegue publico

Inclui un archivo `render.yaml` y una guia en `DEPLOYMENT.md` para publicar la app como servicio web en Render y asociarla a un dominio propio con HTTPS.

Comando de arranque recomendado para hosting:

```bash
streamlit run app/app.py --server.address 0.0.0.0 --server.port $PORT --server.headless true --browser.gatherUsageStats false
```

Si alguna descarga falla por bloqueo anti-bot o DNS, revise `data_raw/download_log.json`. El caso conocido es el XLSX del MHCP: la pagina publica existe, pero el boton de descarga puede activar Radware. El modelo conserva la fuente y usa cifras oficiales resumidas por BanRep/MHCP.

## Datos base principales

- PIB y componentes: DANE, cuentas nacionales trimestrales, IV trimestre de 2025.
- TRM: Datos Abiertos Colombia / Superintendencia Financiera, vigente al 24 de abril de 2026.
- Inflacion: DANE IPC, marzo de 2026.
- Tasa de politica monetaria: Banco de la Republica, vigente desde el 1 de abril de 2026.
- Balanza de pagos: Banco de la Republica, IV trimestre de 2025.
- Variables externas y proxies: Fed H.15, FRED/EIA, CountryEconomy y Trading Economics cuando el portal oficial no ofrece descarga simple en esta sesion.

## Limitacion importante

Este es un modelo estructural simplificado para simulacion comparativa, no un pronostico oficial de la TRM. Los parametros conductuales son editables y se documentan como supuestos calibrables.
