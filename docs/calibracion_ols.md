# Calibración OLS de elasticidades comerciales

Script: `src/calibrate.py`. Fuente: `data_processed/quarterly_master.csv`
(84 trimestres, 2005-2025; 80 observaciones tras la diferencia interanual).

## Metodología

- **Diferencias logarítmicas interanuales** (Δ₄ ln xₜ = ln xₜ − ln xₜ₋₄) para
  remover estacionalidad y evitar regresión espuria sobre series no
  estacionarias en niveles.
- **Tipo de cambio real proxy**: TRM nominal deflactada por el deflactor del
  PIB (PIB nominal / PIB real). Sin precios externos, el factor foráneo se
  absorbe en la tendencia y se elimina al diferenciar.
- **OLS con errores estándar clásicos**, calculados con numpy (sin statsmodels
  para no re-agregar la dependencia al deploy). Es un script offline: su salida
  se cablea manualmente a `DEFAULT_PARAMETERS`.

## Resultados

### 1. Demanda de importaciones: Δln(M) ~ Δln(Y) + Δln(TRM_real)

| Parámetro | Estimado | SE | Interpretación |
|---|---:|---:|---|
| `eta_import_y` | **+2.70** | 0.18 | Elasticidad ingreso de M. Altamente significativo. R²=0.77. |
| `eta_import_q` | **−0.006** | 0.058 | Elasticidad precio de M. **No significativo** (t≈0.1). |

**Lectura:** las importaciones colombianas son **muy procíclicas** (suben 2.7%
por cada 1% de aumento del ingreso) pero **precio-inelásticas en el corto
plazo**: la TRM no tiene efecto detectable sobre el volumen real de
importaciones una vez se controla por ingreso. Esto es coherente con una
canasta importadora dominada por bienes de capital e intermedios poco
sustituibles.

### 2. Demanda de exportaciones: Δln(X) ~ Δln(TRM_real)

| Especificación | `eta_export_q` | SE | R² | Muestra |
|---|---:|---:|---:|---|
| Sin control (naive) | **−0.28** | 0.083 | 0.13 | 2005-2025 (n=80) |
| **+ control Brent** | **+0.25** | 0.096 | 0.52 | 2005-2016 (n=43) |
| + control índice commodity | +0.14 | 0.092 | 0.45 | 2005-2016 (n=43) |

**Lectura:** sin control, el coeficiente sale negativo, contrario a la teoría
(una depreciación debería subir exportaciones). Es el problema clásico del
**exportador de commodities con variable omitida**: las exportaciones
colombianas (petróleo, carbón, café) y la TRM están ambas dirigidas por el
mismo factor de términos de intercambio. Cuando cae el precio del commodity,
caen las exportaciones **y** se deprecia el peso simultáneamente → correlación
negativa espuria.

**Resolución (P32):** al agregar un control de precios de commodities
(Brent, de la fuente World Bank Pink Sheet vía `src/external_data.py`), el
factor de términos de intercambio se absorbe y `eta_export_q` **recupera el
signo positivo esperado: +0.25 (SE 0.10)**, con el petróleo fuertemente
significativo (β_oil=+0.21) y el R² subiendo de 0.13 a 0.52. Esto confirma
el diagnóstico de variable omitida y entrega una elasticidad estructural
usable. **Limitación:** la copia del Pink Sheet disponible en el entorno solo
llegó hasta 2016Q3, así que la regresión con control usa la submuestra
2005-2016 (43 obs, con buena variación: auge de commodities 2011-14 e inicio
del desplome petrolero 2014-16). El fetcher `fetch_commodities_quarterly()`
obtiene la serie completa donde el CDN sirva el archivo actualizado.

## Decisión de calibración

| Parámetro | Anterior | Nuevo | Justificación |
|---|---:|---:|---|
| `eta_import_y` | 1.35 | **2.70** | Estimado directo, bien identificado (SE bajo, R² alto). |
| `eta_import_q` | 0.25 | **0.10** | Estimado ≈0; se usa 0.10 (extremo superior del IC) para conservar un canal mínimo de expenditure-switching que el modelo necesita para que la TRM cierre el balance comercial. |
| `eta_export_q` | 0.45 | **0.25** | Estimado +0.25 (SE 0.10) con control de commodities (Brent), muestra 2005-2016. Reemplaza el ancla de juicio 0.30 (P29) por un valor empíricamente identificado con el signo correcto. |
| `output_rate_sensitivity` | 0.50 | 0.50 | **No estimado**: requiere serie de tasa de interés real trimestral que no está en el panel. Se mantiene el valor tipo Taylor. |

## Implicación económica del hallazgo

La calibración empírica revela un **canal de expenditure-switching asimétrico**
en datos colombianos:
- **Importaciones precio-inelásticas** (`eta_import_q` ≈ 0): el volumen real de
  importaciones no responde a la TRM en el corto plazo.
- **Exportaciones sí responden** (`eta_export_q` ≈ +0.25), pero solo se aprecia
  una vez se controla por el precio de commodities; sin ese control la relación
  queda enmascarada por el ciclo de términos de intercambio.

El canal de ajuste comercial vía TRM existe pero es **moderado y recae casi
enteramente del lado exportador**. Esto implica que la TRM debe moverse de forma
apreciable para cerrar desbalances comerciales — consistente con la alta
volatilidad observada del peso colombiano.

## Banda de sensibilidad

El default de la banda de proyección (`project_with_sensitivity`) se fijó en
**±13%**, que corresponde a ~2 errores estándar relativos de la elasticidad
mejor identificada (`eta_import_y`: 2·0.18/2.70 ≈ 13%). Reemplaza el ±25%
arbitrario anterior por una magnitud con interpretación econométrica.

## Limitaciones declaradas

- Endogeneidad de la TRM no corregida con IV (sería sobre-ingeniería para una
  calibración). Los coeficientes son asociaciones condicionales.
- La elasticidad de exportaciones controla por precio de commodities pero aún
  omite demanda externa (PIB de socios comerciales). El fetcher
  `fetch_partner_gdp_annual()` en `src/external_data.py` deja lista esa serie
  (World Bank WDI) para una extensión futura; no se incorporó aún por el
  desajuste de frecuencia (WDI es anual, el panel trimestral).
- La regresión con control de commodities usa 2005-2016 por la copia del Pink
  Sheet disponible; conviene re-estimar con la serie completa cuando el CDN
  sirva el archivo actualizado.
- `output_rate_sensitivity` y los parámetros financieros (`*_uip_*`, `*_bp_*`)
  siguen siendo supuestos, no estimados.
