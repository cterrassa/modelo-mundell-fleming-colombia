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

| Especificación | `eta_export_q` (TRM) | SE | R² | Otros coeficientes |
|---|---:|---:|---:|---|
| Sin control (naive) | **−0.28** | 0.083 | 0.13 | — |
| + control Brent solo | +0.18 | 0.099 | 0.43 | β_oil +0.23 |
| + índice commodity full | +0.01 | 0.091 | 0.35 | β_com +0.19 |
| **+ commodity + demanda externa** | **+0.03** (≈0, no signif.) | 0.077 | 0.54 | β_com +0.10; **β_Y\*ext +2.22** (SE 0.39) |

*Muestra completa 2006-2025 (n=80), salvo el naive. Series: índice de
commodities (FRED IMF PCPS: Brent, carbón Newcastle, café Other Milds, níquel,
metales) y demanda externa (PIB real de EE.UU., Alemania, Brasil, México
ponderado por exportaciones), todas al presente vía curl a FRED.*

**Lectura:** sin control, el coeficiente sale negativo, contrario a la teoría
(una depreciación debería subir exportaciones). Es el problema clásico del
**exportador de commodities con variable omitida**: las exportaciones
colombianas (petróleo, carbón, café) y la TRM están ambas dirigidas por el
mismo factor de términos de intercambio. Cuando cae el precio del commodity,
caen las exportaciones **y** se deprecia el peso simultáneamente → correlación
negativa espuria.

**Resolución (P32 → P33, búsqueda exhaustiva):** una primera versión usó solo
Brent como control y obtuvo `eta_export_q` = +0.18, pero eso era un **artefacto
de control incompleto**. Al hacer la búsqueda exhaustiva de datos (FRED espeja
las series de commodities del IMF PCPS hasta el presente, y hay PIB trimestral
de los socios grandes), se pudo armar el set de control COMPLETO: índice de
commodities full (petróleo, carbón, café, níquel, metales) **más demanda
externa** (PIB de socios ponderado por exportaciones).

Con el set completo, la elasticidad de exportaciones a la TRM **colapsa a cero
(+0.03, SE 0.08, no significativa)**. Los verdaderos motores de las
exportaciones reales colombianas son:
- **Demanda externa**, con elasticidad **+2.22** (SE 0.39, altamente
  significativa): las exportaciones siguen el ciclo de los socios comerciales.
- **Precios de commodities**, con coeficiente +0.10-0.19.

El R² sube de 0.13 (naive) a 0.54 (set completo). El +0.18 del control-solo-Brent
era spurious: el petróleo no absorbía del todo el factor de demanda/términos de
intercambio, dejando carga residual falsa sobre la TRM.

**Interpretación económica (pesimismo de elasticidades):** es el patrón clásico
de un exportador de commodities. Colombia exporta petróleo, carbón y café a
precios mundiales en cantidades reales determinadas por capacidad y demanda
externa; el **nivel del peso casi no cambia el volumen exportado**. El canal de
ajuste comercial vía tipo de cambio es débil en ambos lados (importaciones
precio-inelásticas, exportaciones volumen-inelásticas a la TRM). **Implicación
clave para el modelo: la TRM colombiana se ajusta principalmente por el canal
financiero (paridad de tasas, prima de riesgo, petróleo) y no por el comercial**
— consistente con cómo se comporta el peso en la realidad.

## Decisión de calibración

| Parámetro | Anterior | Nuevo | Justificación |
|---|---:|---:|---|
| `eta_import_y` | 1.35 | **2.70** | Estimado directo, bien identificado (SE bajo, R² alto). |
| `eta_import_q` | 0.25 | **0.10** | Estimado ≈0; se usa 0.10 (extremo superior del IC) para conservar un canal mínimo de expenditure-switching que el modelo necesita para que la TRM cierre el balance comercial. |
| `eta_export_q` | 0.45 | **0.10** | Con set de control completo (commodities + demanda externa) la elasticidad a la TRM es estadísticamente cero (+0.03, SE 0.08). Se usa 0.10 (dentro del IC) para conservar un canal mínimo de expenditure-switching que el modelo necesita. Los motores reales son demanda externa (+2.2) y commodities. |
| `output_rate_sensitivity` | 0.50 | 0.50 | **No estimado**: requiere serie de tasa de interés real trimestral que no está en el panel. Se mantiene el valor tipo Taylor. |

## Implicación económica del hallazgo

La calibración empírica revela un **canal de expenditure-switching muy débil en
ambos lados** del comercio colombiano:
- **Importaciones precio-inelásticas** (`eta_import_q` ≈ 0): el volumen real de
  importaciones no responde a la TRM en el corto plazo.
- **Exportaciones volumen-inelásticas a la TRM** (`eta_export_q` ≈ 0 con control
  completo): el volumen exportado lo determinan la demanda externa (elast. +2.2)
  y los precios de commodities, no el nivel del peso.

Es decir, **el tipo de cambio NO cierra el balance comercial por cantidades** en
el corto plazo (cuasi-incumplimiento de Marshall-Lerner en datos colombianos).
La consecuencia para el modelo es importante: la TRM colombiana se ajusta
fundamentalmente por el **canal financiero** (paridad de tasas, prima de riesgo,
precio del petróleo) y no por el comercial. El modelo ya captura esos canales
financieros (UIP, riesgo, oil); la calibración confirma que ahí está el ajuste,
y explica la alta volatilidad del peso frente a choques financieros y de
commodities.

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
- El control primario de petróleo (FRED Brent) cubre la muestra completa
  2006-2025; el índice commodity ponderado (Pink Sheet) solo llega a 2016 y se
  usa como robustez. El carbón colombiano, café y oro del Pink Sheet quedan
  limitados a 2016 hasta conseguir una copia actualizada del archivo.
- `output_rate_sensitivity` y los parámetros financieros (`*_uip_*`, `*_bp_*`)
  siguen siendo supuestos, no estimados.
