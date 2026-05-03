# Metodologia

## Que hace y que no hace este simulador

Es una herramienta academica de estatica comparativa que implementa el
**modelo Mundell-Fleming de economia abierta pequena** aplicado a Colombia. Tres usos
validos:

- Reproducir resultados textbook de Mundell-Fleming flexible (movilidad
  perfecta de capitales).
- Explorar el comportamiento bajo movilidad imperfecta calibrada con datos
  colombianos.
- Proyectar de forma deterministica a 5 anos el equilibrio bajo escenarios
  predefinidos, anclado al ultimo ano observado.

NO pronostica la TRM, NO usa Monte Carlo, NO genera intervalos estocasticos.

## Modelo

### Convencion de variables

- Y = PIB real trimestral (COP miles de millones, precios constantes 2015).
- TRM = COP por USD. **Mayor TRM = peso depreciado** (convencion Banrep).
- r = tasa de interes domestica (% anual).
- r* = tasa externa (Fed funds).
- C, I, G, X, M = componentes del gasto agregado en COP bn reales.

### Bloque comun (estatica comparativa)

```text
Y = C + I + G + NX + residuo
C = C0 + c (Y - T)
I = I0 (1 - b (r - r0))
NX = X(TRM, oil) - M(TRM, Y) + NX_aut
X = X0 (1 + eta_export_q * q + eta_oil_export * oil_pct)
M = M0 (1 + eta_import_y * dY/Y0 - eta_import_q * q)
```

Donde `q = TRM/TRM0 - 1` es la depreciacion del peso, `c` la propension
marginal a consumir y `b` la sensibilidad de la inversion a la tasa real.

### Diagrama IS\*-LM\* en plano (Y, TRM) — economia abierta pequena

El simulador grafica el equilibrio en el plano `(Y, TRM)`, que es el plano
canonico para el modelo MF de economia abierta pequena con
movilidad de capitales:

- **Curva IS\* (azul, pendiente positiva).** Para cada nivel de Y, despeja
  la TRM que hace cumplir la identidad
  `Y = C + I + G + NX(TRM, Y) + residuo`. Mayor Y demandado por el gasto
  requiere mayor TRM (peso depreciado) que genere el NX adicional. Los
  choques fiscales (G, T) y los choques reales (Brent, NX_aut) desplazan
  IS\*.

- **Curva LM\* (verde, vertical).** Es el Y consistente con el mercado
  monetario dada la tasa local r y la oferta monetaria M. En forma cerrada:
  `Y_LM = Y0 (1 + ((r - r0) + kappa_M * M%) / kappa_Y)`. Choques monetarios
  o externos (Fed, prima de riesgo) desplazan LM\*.

- **Equilibrio:** interseccion. La flecha roja marca el movimiento del
  equilibrio entre el escenario base y el escenario simulado.

### Movilidad perfecta (economia abierta pequena puro)

La curva BP es horizontal (no se grafica): la tasa local queda anclada por
paridad descubierta de intereses ajustada por riesgo:

```text
r = r* + risk_premium
```

Resolucion en forma cerrada (sin iteracion):
1. r queda determinado por UIP.
2. Y_LM queda determinado por la LM invertida dada r y M.
3. TRM absorbe el desbalance de la IS via NX. Resolvemos analiticamente
   el q que hace `NX(q) = NX_required` en el punto Y_LM.

Resultados canonicos esperados:
- **Politica fiscal:** ΔG > 0 desplaza IS\* hacia abajo (para cada Y, hace
  falta menor TRM porque G ya cubre parte del gasto). LM\* sin cambio
  (M, r* sin cambio). Equilibrio: Y constante, TRM cae (peso aprecia).
- **Politica monetaria:** ΔM > 0 desplaza LM\* hacia la derecha (Y_LM
  mayor para r dada). IS\* sin cambio. Equilibrio: Y sube, TRM sube
  (depreciacion).
- **Choque a tasa Banrep:** sin efecto. La tasa esta anclada por UIP.

### Movilidad imperfecta (calibracion empirica para Colombia)

La tasa local se desvia de UIP. Los flujos de capital responden con
elasticidad finita al diferencial de tasas. La TRM ajusta proporcional a
un saldo residual de balanza de pagos. Se resuelve por iteracion de punto
fijo (12 pasos).

El banco central sigue una regla de Taylor simplificada:

```text
r = r0 + delta_policy_rate - kappa_M (M%) + kappa_Y (gap_Y%)
```

En el plano (Y, TRM), el equilibrio se grafica igual: IS\* y LM\* se
trazan usando la tasa endogena que el solver encontro. La unica diferencia
con perfecta es la posicion de las curvas; el plano y la convencion son
identicos.

### Choques (Shock dataclass, 8 dimensiones)

Politica domestica:
- `government_spending_pct` (G, % del G base)
- `tax_pct_of_gdp` (T, % del PIB)
- `money_supply_pct` (M3, %)
- `domestic_policy_rate_bp` (Banrep, puntos basicos; sin efecto en perfecta)

Externos:
- `foreign_rate_bp` (Fed funds, puntos basicos)
- `risk_premium_bp` (prima Colombia, puntos basicos)
- `oil_price_pct` (Brent, %)
- `nx_autonomous_pct` (choque a NX, % del PIB; consolida terminos de
  intercambio, demanda externa, X/M directos)

### Parametros conductuales

11 parametros editables guardados en `data_processed/parameters.csv`:
`mpc`, `investment_rate_sensitivity`, `money_rate_sensitivity` (kappa_M),
`output_rate_sensitivity` (kappa_Y, calibrado en 0.50 - Taylor estandar),
`eta_export_q`, `eta_import_q`, `eta_import_y`, `eta_oil_export`,
`capital_flow_sensitivity_usd_m_per_pp`, `exchange_rate_uip_sensitivity`,
`exchange_rate_bp_sensitivity`. Los ultimos tres solo aplican en el modo
imperfecta.

## Datos

### En vivo (con cache)

| Serie | Fuente | Endpoint | Cache |
|---|---|---|---|
| TRM diaria | Datos Abiertos / Superfinanciera | Socrata SODA | 1 h |
| Fed funds efectiva | FRED | DFF | 1 h |
| Brent | FRED / EIA | DCOILBRENTEU | 1 h |

Si una fuente falla, el badge dice "snapshot" y se usa el valor del
calibrado base. La app no falla silenciosamente.

### Snapshot fijo

| Serie | Fuente | Frecuencia | Ultimo dato |
|---|---|---|---|
| PIB y componentes (C, I, G, X, M) reales y nominales | DANE Cuentas Nacionales | Trimestral | 2025Q4 |
| IPC e inflacion | DANE | Mensual | 2026-03 |
| Tasa de politica monetaria | Banco de la Republica | Evento | 2026-04-01 |
| Cuenta corriente y financiera | Banco de la Republica | Trimestral | 2025Q4 |
| Prima de riesgo Colombia, M3, reservas | Proxies publicos (CountryEconomy, TradingEconomics) | Mensual / Diaria | 2026-Q1 |

La matriz completa de fuentes y URLs esta en `data_processed/source_matrix.csv`.

## Validacion

`outputs/validation_tests.csv` contiene 17 pruebas de signos contra teoria
(8 perfecta + 9 imperfecta). Todas deben pasar tras cualquier cambio al
modelo:

- Subida prima de riesgo deprecia
- Subida tasa Fed deprecia
- Caida petroleo deprecia
- Mejora externa aprecia
- Expansion monetaria deprecia y sube Y
- Perfecta: expansion fiscal no mueve Y, aprecia, tasa Banrep no efecto
- Imperfecta: subida tasa Banrep aprecia, expansion fiscal sube Y

Verificacion adicional implicita: la curva IS\* construida para el chart
debe pasar exactamente por el equilibrio que devuelve `simulate()`. Esta
consistencia se valida automaticamente cada vez que se renderiza el chart.

## Proyeccion a 5 anos

Module `src/mf_projection.py`. Cada ano aplica un choque sostenido de
exogenos sobre la calibracion base y resuelve el equilibrio estatico. Los
choques no se acumulan entre anos; cada periodo es independiente.

Escenarios predefinidos: Base, Expansion fiscal sostenida, Subida tasa Fed
sostenida, Ciclo petrolero adverso, Subida prima de riesgo.

La tabla consolidada en la app combina:
- 5 anos historicos: suma anual de los 4 trimestres de `quarterly_master.csv`.
- 5 anos proyectados: el % cambio del modelo aplicado al ultimo ano
  observado (anclaje, evita estacionalidad de Q4).

## Backtesting

Module `src/backtest.py`. Para cada trimestre desde el primero disponible
hasta el ultimo, alimenta el modelo con `Delta_Fed_bp` y `Delta_Brent_pct`
observados, predice el cambio % de TRM, compara con observado.

Reporta RMSE, MAE, correlacion y residuos. Series usadas:
- TRM diaria de Datos Abiertos (promediada a trimestres).
- Fed funds (FRED DFF).
- Brent (FRED DCOILBRENTEU).

Limitaciones reconocidas:
- El modelo es estatico-comparativo: cada periodo es independiente.
- No incluye prima de riesgo Colombia (sin serie publica fiable de calidad).
- No captura choques de oferta domesticos (COVID 2020Q2, paro 2021,
  inflacion 2022).

Estos son limites teoricos del modelo, no bugs.

## Corto plazo vs largo plazo

El modelo Mundell-Fleming es de **corto plazo** por construccion: precios
fijos, Y puede desviarse de Y_n. Para contextualizar pedagogicamente, el
modulo `src/long_run.py` implementa el equilibrio de **largo plazo** del
mismo marco abierto pequeno (marco de largo plazo, no de corto plazo):

```text
Y = Y_n          (exogeno, definido por capital y trabajo)
C = C(Y_n - T)
I = I(r),  r = r* + prima de riesgo
NX = Y_n - C - I - G - residuo
e ajusta para que NX(e) cumpla la igualdad
```

Resultados clave que cambian entre SR y LR:

- **Politica monetaria es neutral en LR** (clasica neutralidad de Friedman):
  un choque a M solo mueve precios y tipo de cambio nominal, no Y. En SR si
  mueve Y porque los precios no han ajustado.
- **Choques externos** (Fed, prima de riesgo) tienen efecto solo via la
  inversion (`I` responde a `r = r* + risk`). En SR amplifican el efecto via
  la respuesta de la LM a la tasa (Y se desvia de Y_n).
- **Politica fiscal**: en SR-perfecta y en LR ya da el resultado canonico
  (Y constante, NX absorbe). En SR-imperfecta tambien mueve Y.

El tab "Corto vs largo plazo" muestra la comparacion lado a lado para el
choque activo. El SR respeta el modo de movilidad seleccionado; el LR siempre
asume movilidad perfecta porque es el referente teorico de economia abierta pequena de largo plazo.

## Limitaciones generales

El modelo es comparativo-estatico y linealizado alrededor del estado base.
No incorpora expectativas racionales, curva de Phillips completa, reaccion
endogena de politica fiscal, ni microestructura cambiaria. Las elasticidades
son calibrables y se documentan como supuestos editables.
