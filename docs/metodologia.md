# Metodologia

## Definicion de nivel actual

Se usa la ultima observacion oficial o publica disponible al 24 de abril de 2026. Para cuentas nacionales, la ultima publicacion del DANE disponible corresponde al IV trimestre de 2025, publicada el 16 de febrero de 2026. Para TRM, la base Socrata de Datos Abiertos llega al 24 de abril de 2026.

## Fuentes

La matriz completa esta en `data_processed/source_matrix.csv`. Las fuentes de mayor prioridad son DANE, Banco de la Republica, Superintendencia Financiera / Datos Abiertos y MHCP. Cuando el acceso directo fue bloqueado o no expuso descarga simple, se uso proxy publico y se marco como tal.

## Modelo

El modelo usa los bloques clasicos de Mundell-Fleming:

```text
Y = C + I + G + NX
C = C0 + c(Y - T)
I = I0 - b(r - r0)
NX = X(q, Y*, petroleo, terminos de intercambio) - M(q, Y)
BP = CA + KA + errores_y_omisiones
```

La TRM se ajusta por una combinacion de paridad descubierta ajustada por riesgo y presiones de balanza de pagos:

```text
Delta E / E =
  sensibilidad_uip * Delta(i* + riesgo + depreciacion_esperada - i)
  + factores_reales
  - sensibilidad_bp * (BP / PIB_usd)
```

La convencion es: mayor `E` significa depreciacion del peso colombiano. Un superavit de balanza de pagos reduce `E`; un deficit aumenta `E`.

## Calibracion

Los niveles base se guardan en `data_processed/base_calibration.csv`. Las variables observadas se separan de proxies y transformaciones. Los parametros conductuales se guardan en `data_processed/parameters.csv` y son editables en el codigo o desde la app.

## Validacion

Las pruebas de signos se guardan en `outputs/validation_tests.csv`. El modelo exige que:

- mayor prima de riesgo deprecie la TRM;
- mayor tasa externa deprecie la TRM;
- mayor tasa domestica aprecie la TRM en el corto plazo;
- menor precio del petroleo deprecie la TRM;
- mejores exportaciones aprecien la TRM;
- expansion monetaria deprecie la TRM.

## Limitaciones

El modelo es comparativo-estatico y linealizado alrededor del estado base. No incorpora expectativas racionales, curva de Phillips completa, reaccion endogena de politica fiscal ni microestructura cambiaria. La prima de riesgo, M3, Brent y terminos de intercambio usan proxies publicos cuando el portal oficial no permitio descarga directa en esta sesion.
