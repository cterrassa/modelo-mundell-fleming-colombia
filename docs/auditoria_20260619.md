# Auditoría exhaustiva — App Modelo Mundell-Fleming Colombia

**Fecha:** 2026-06-19 · **Método:** dos ciclos de auditoría multi-agente
(4 auditores por dominio + verificación adversarial de cada hallazgo ALTO/MEDIO)
seguidos de remediación verificada. · **Commits:** P34 (ciclo 1), P35 (ciclo 2).

---

## 1. Veredicto

**Calificación global: 91 / 100** — *Aprobado, listo para producción.*

Partió de **81/100** (preliminar, ciclo 1) → **88/100** (tras remediar el ciclo 1)
→ **91/100** (tras cerrar las brechas de reproducibilidad del ciclo 2).

| Dimensión | Nota | Sustento |
|---|---:|---|
| Correctitud del modelo / teoría | 95 | Resultados canónicos exactos en los 3 regímenes; UIP exacta; identidad `Y=C+I+G+NX` sin drift; solver convergente; neutralidad de largo plazo correcta. 22 pruebas de signo verdes. |
| Calibración / econometría | 88 | Elasticidades estimadas por OLS con SE/R² y provenance trazable; hallazgo central honesto (`eta_export_q≈0`, demanda externa +2.2). Resta: parámetros financieros aún supuestos. |
| Datos / fidelidad / consistencia | 90 | Fuentes inventariadas y trazables; fallback a snapshot robusto; bug ALTO de anualización de año parcial **corregido**; diccionario de datos completado. |
| Arquitectura / código / pruebas | 93 | Modelo desacoplado de UI; fetchers con degradación elegante; 52 tests + AppTest verdes; pyflakes limpio. |
| Reproducibilidad / despliegue | 88 | Deps y Python pineados (Render `PYTHON_VERSION` + `.python-version` + `runtime.txt`); ETL ahora reproduce los CSV de parámetros (test golden). |
| Producto / UX / visualización | 90 | 3 regímenes, MFMP habilitado y etiquetado, gráficos corregidos (colores por polaridad, banda ±13% coherente), responsive móvil, onboarding por expanders. |

---

## 2. Hallazgos consolidados (30+ → 7 causas raíz)

| Causa raíz | Severidad máx. | Estado |
|---|---|---|
| CR-1 `calibrate.py` imprimía calibración vieja como "actual" | BAJO | ✅ Resuelto (lee `DEFAULT_PARAMETERS` en vivo) |
| CR-2 Banda ±13% mal etiquetada (±25%) y mal atribuida | MEDIO | ✅ Resuelto (constante única; framing honesto: barrido sobre magnitud del choque) |
| CR-3 ETL omitía el régimen "fijo" → CSV desincronizados | ALTO | ✅ Resuelto (`MOBILITY_OPTIONS`; CSV 30/22; `tests/test_signs.py`) |
| CR-4 (F2) Año parcial anualizado como completo | ALTO | ✅ Resuelto (exige 4 trimestres; `last_observed_year` de años completos) |
| CR-5 Build no reproducible (deps + Python sin pin) | ALTO | ✅ Resuelto (rangos en `requirements.txt`; `PYTHON_VERSION` en `render.yaml`) |
| CR-6 Documentación desfasada del código | ALTO→MEDIO | ✅ Resuelto (régimen fijo, Shock 10 dims, 22 signos, demanda externa, sin función fantasma) |
| CR-7 (VIZ-02) Colores del gráfico de impacto invertidos | MEDIO | ✅ Resuelto (color por polaridad por variable) |
| N-1 ETL no reproducía `parameters.csv` (provenance a mano) | MEDIO | ✅ Resuelto (provenance embebida + test golden) |
| NEW-01 `data_dictionary.csv` incompleto | MEDIO | ✅ Resuelto (14 → 25 variables) |

Hallazgos que **no se tocaron** (con justificación): el núcleo econométrico
(elasticidades, regímenes, identidad) por estar correcto y verificado; la
magnitud ±13% (la aritmética es correcta, el defecto era de atribución/etiqueta);
`MF-07` (depreciación amplia ante choque monetario en perfecta) por ser
comportamiento teórico correcto dadas las elasticidades comerciales ~0.

---

## 3. MFMP (requerimiento explícito)

La opción de **simular el Marco Fiscal de Mediano Plazo** queda **habilitada y
clara** en la pestaña "Cuentas nacionales y proyecciones" (escenario "MFMP
proxy"). Al seleccionarla se muestra un `st.warning` que aclara que es un proxy
ilustrativo (supuestos consistentes con BanRep y FMI WEO), **no cifras oficiales
del MHCP**, y cómo reemplazar `data_processed/mfmp_proxy_scenario.csv` con el
documento oficial cuando esté disponible (el MHCP no es alcanzable por curl desde
el entorno de desarrollo; DNS bloqueado).

---

## 4. Verificación final

- **52/52** pruebas unitarias (`pytest tests/`), incluyendo las **22 pruebas de
  signo** (9 perfecta + 8 imperfecta + 5 fijo) ahora ejecutadas como aserciones.
- **AppTest** (`streamlit.testing.v1`): 0 excepciones.
- **pyflakes** limpio (salvo reexports intencionales `bp`/`pct`).
- ETL reproducible: `test_parameters_csv_matches_etl` blinda la provenance.

---

## 5. Backlog remanente (no bloqueante)

- Integrar prima de riesgo Colombia (proxy EMBI/`BAMLEMCBPIOAS`) y/o REER (`RBCOBIS`)
  al backtest — series ya confirmadas alcanzables; mejora la utilidad para un
  analista Banrep/MHCP. Esfuerzo: medio/grande.
- Reemplazar el proxy MFMP por las cifras oficiales del MHCP cuando se obtengan.
- Oro puro y PIB trimestral de China no disponibles por curl (documentado).
