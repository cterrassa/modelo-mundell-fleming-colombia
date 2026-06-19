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

| Parámetro | Estimado | SE | Interpretación |
|---|---:|---:|---|
| `eta_export_q` | **−0.28** | 0.083 | **Signo equivocado** vs teoría (se espera +). R²=0.13. |

**Lectura:** el coeficiente sale negativo, contrario a la teoría (una
depreciación debería subir exportaciones). Es el problema clásico del
**exportador de commodities con variable omitida**: las exportaciones
colombianas (petróleo, carbón, café) y la TRM están ambas dirigidas por el
mismo factor de términos de intercambio. Cuando cae el precio del commodity,
caen las exportaciones **y** se deprecia el peso simultáneamente → correlación
negativa espuria. El coeficiente **no es una elasticidad estructural usable**.

## Decisión de calibración

| Parámetro | Anterior | Nuevo | Justificación |
|---|---:|---:|---|
| `eta_import_y` | 1.35 | **2.70** | Estimado directo, bien identificado (SE bajo, R² alto). |
| `eta_import_q` | 0.25 | **0.10** | Estimado ≈0; se usa 0.10 (extremo superior del IC) para conservar un canal mínimo de expenditure-switching que el modelo necesita para que la TRM cierre el balance comercial. |
| `eta_export_q` | 0.45 | **0.30** | El estimado naive es wrong-signed (commodities). Se ancla por debajo del valor previo para reflejar la débil respuesta de exportaciones de commodities a la TRM, sin usar el coeficiente contaminado. |
| `output_rate_sensitivity` | 0.50 | 0.50 | **No estimado**: requiere serie de tasa de interés real trimestral que no está en el panel. Se mantiene el valor tipo Taylor. |

## Implicación económica del hallazgo

La calibración empírica revela que **el canal de expenditure-switching vía TRM
es débil en datos colombianos**: las importaciones no responden al precio y la
respuesta de exportaciones está confundida por commodities. Esto significa que
en el modelo la TRM debe moverse bastante para cerrar desbalances comerciales
pequeños — lo que es consistente con la alta volatilidad observada del peso.

## Banda de sensibilidad

El default de la banda de proyección (`project_with_sensitivity`) se fijó en
**±13%**, que corresponde a ~2 errores estándar relativos de la elasticidad
mejor identificada (`eta_import_y`: 2·0.18/2.70 ≈ 13%). Reemplaza el ±25%
arbitrario anterior por una magnitud con interpretación econométrica.

## Limitaciones declaradas

- Endogeneidad de la TRM no corregida con IV (sería sobre-ingeniería para una
  calibración). Los coeficientes son asociaciones condicionales.
- La elasticidad de exportaciones omite demanda externa (PIB socios) por falta
  de serie en el panel.
- `output_rate_sensitivity` y los parámetros financieros (`*_uip_*`, `*_bp_*`)
  siguen siendo supuestos, no estimados.
