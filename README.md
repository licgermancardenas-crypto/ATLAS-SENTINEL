# ATLAS SENTINEL

Asistente de seguridad para conductores y planificación urbana en Buenos Aires (nombre de venta: **SIGE-BA**). Cruza delitos geolocalizados con datos de transporte (colectivos, EcoBici, subte), alumbrado público y siniestros viales para estimar riesgo por zona y horario — no solo un heatmap estático, sino un modelo núcleo espacio-temporal (grilla H3) del que se desprenden 3 módulos de decisión operativa (patrullas, cámaras, controles de acceso).

Arquitectura técnica completa del modelo: [`arquitectura-sige-ba.pdf`](arquitectura-sige-ba.pdf).

## Estructura

- `pipeline/` — scripts de ingesta y normalización de cada fuente de datos (Fase 1, completa)
- `data/features/` — tablas intermedias post-cruce espacial (hex_maestra, datasets con hex_id asignado) — no versionado en git, se regenera con `src/etl/`
- `src/etl/` — Capa 0: unificación espacio-temporal (grilla H3-8, asignación de hex_id/turno a cada dataset)
- `src/model_core/` — Capa 1: modelo núcleo de riesgo (XGBoost/LightGBM, objetivo Poisson)
- `src/optimization/` — Capa 2: módulos A/B/C (asignación de patrullas, cámaras nuevas, controles de acceso)
- `src/validation/` — Capa 3: SHAP, backtesting, métricas
- `src/export/` — genera los JSON/GeoJSON livianos que consume el dashboard
- `notebooks/` — exploración y validación de datos
- `models/`, `api/`, `web/` — carpetas del scaffold original; el plan vigente las reemplaza por `src/*` + `dashboard/` (Next.js, separado) — ver el PDF de arquitectura

## Fuentes de datos

| Fuente | Origen | Tamaño real |
|---|---|---|
| Delitos CABA | data.buenosaires.gob.ar/dataset/delitos | ~180MB (2016-2025) |
| Siniestros viales | data.buenosaires.gob.ar/dataset/victimas-siniestros-viales | ~16MB |
| Alumbrado LED | data.buenosaires.gob.ar/dataset/alumbrado-led | 9.4MB |
| Colectivos GTFS | data.buenosaires.gob.ar/dataset/colectivos-gtfs | 209MB |
| EcoBici recorridos | data.buenosaires.gob.ar/dataset/bicicletas-publicas | 2.0GB comprimido (crudo, no se guarda descomprimido) |
| Subte Molinetes | data.buenosaires.gob.ar/dataset/subte-viajes-molinetes | 1.1GB comprimido (crudo, no se guarda descomprimido) |
| Cámaras de control vehicular | data.buenosaires.gob.ar/dataset/camaras-fijas-control-vehicular | 15KB |
| Cajeros automáticos | data.buenosaires.gob.ar/dataset/cajeros-automaticos | 214KB |
| Establecimientos educativos | data.buenosaires.gob.ar/dataset/establecimientos-educativos | 1.1MB |
| Hospitales | data.buenosaires.gob.ar/dataset/hospitales | 15.6KB |
| Divisiones comisarías vecinales | data.buenosaires.gob.ar/dataset/divisiones-comisarias-vecinales | 2.5MB |
| Trenes GTFS | data.buenosaires.gob.ar/dataset/trenes-gtfs | 7.5MB descomprimido |
| Comisarías (ubicación puntual) | data.buenosaires.gob.ar/dataset/comisarias-policia-ciudad | 10KB |
| Universidades | data.buenosaires.gob.ar/dataset/universidades | 37KB |
| Espacios verdes públicos | data.buenosaires.gob.ar/dataset/espacios-verdes | 15MB |
| Socioeconómico por comuna (NBI + hacinamiento) | data.buenosaires.gob.ar (Instituto de Vivienda) | <1KB |
| Barrios (polígonos) | data.buenosaires.gob.ar/dataset/barrios | 651KB |
| Radios censales (Censo 2010) | data.buenosaires.gob.ar/dataset/informacion-censal-por-radio | 2.5MB |
| Población por comuna y por barrio | data.buenosaires.gob.ar/dataset/estructura-demografica y /barrios | <1KB c/u |
| Calles (callejero, con jerarquía vial) | data.buenosaires.gob.ar/dataset/calles | 10.6MB |
| Accesos por autopista (peajes/pórticos) | data.buenosaires.gob.ar/dataset/peajes-porticos-autopistas | <1KB |
| Estadios | data.buenosaires.gob.ar/dataset/estadios | 10KB |
| Eventos masivos (permisos) | data.buenosaires.gob.ar/dataset/permisos-eventos-masivos | ~230KB (5 años) |
| Clima diario | NASA POWER API (power.larc.nasa.gov) | ~130KB |

Los datos crudos no se versionan en git — se descargan localmente con los scripts de `pipeline/`.

## Estado de la ingesta

Las 6 fuentes previstas para la Fase 1 (riesgo + transporte) están completas, más 6 fuentes de contexto adicionales (POIs, cámaras, trenes).

| Fuente | Filas | Notas |
|---|---|---|
| Delitos | 1.353.136 | 2016-2025 |
| Siniestros viales | 63.081 hechos + 75.197 víctimas | 2019-2025 |
| Alumbrado LED | 102.700 luminarias | cobertura completa 15 comunas |
| Colectivos GTFS | 43.594 paradas, 1.052 ramales | feed sin actualizar desde 2019-09-30 |
| EcoBici | 48.222.663 viajes agregados, 570 estaciones | 2010-2026. Máquina de desarrollo con 3.4GB de RAM — todo se procesa en chunks y se agrega directo a "viajes por estación/hora/día de semana" en vez de guardar cada viaje. 2014 (~2% del histórico) queda afuera por tener un esquema propio sin id de estación ni coordenadas — ver nota en `pipeline/ingest_ecobici.py`. |
| Subte Molinetes | 2.799.213.945 pasajeros agregados, 90 estaciones | 2013-2025. 96.8% geolocalizado (matching por tokens + abreviaturas + alias manuales contra el dataset de estaciones, que usa nombres oficiales distintos a los de molinetes); el 3.2% restante son variantes de corrupción de encoding en nombres con Ñ/Ü — ver nota en `pipeline/ingest_molinetes.py`. |
| Cámaras de control vehicular | 224 | analítica de video + cinemómetros |
| Cajeros automáticos | 1.279 | |
| Establecimientos educativos | 2.767 | reproyectadas desde el sistema plano legacy "0 de Flores" (ver `pipeline/geo_utils.py`), ~100m de margen de error |
| Hospitales | 36 | públicos únicamente; mismo sistema de coordenadas que escuelas |
| Divisiones comisarías vecinales | 45 | son polígonos de zona de patrullaje, no la ubicación puntual de cada comisaría — se guarda el centroide + el polígono original en WKT |
| Comisarías (ubicación puntual) | 75 | complementa lo anterior con la dirección real de cada comisaría, lat/lon directo sin proyección rara |
| Trenes GTFS | 248 paradas, 27 ramales | único dataset que extiende cobertura más allá de CABA hacia el conurbano; feed sin actualizar desde 2020-02-10 |
| Universidades | 153 | lat/lon directo, sin proyección rara esta vez |
| Espacios verdes públicos | 2.176 (plazas, plazoletas, parques) | polígonos — se guarda centroide + WKT original para join espacial futuro |
| Socioeconómico por comuna | 15 comunas | % hogares con NBI + % hacinamiento. Sin coordenadas, se cruza por el campo "comuna" que ya existe en delitos/siniestros/alumbrado |
| Barrios | 48 | polígonos con comuna asignada — unidad intermedia entre comuna (15) y radio censal (3.554) para agrupar/mostrar riesgo |
| Radios censales | 3.554 | Censo 2010 — población total, sexo, viviendas, hogares y % NBI por radio (~800 hab. c/u). Es el denominador que faltaba para "delitos per cápita" y la unidad más fina disponible con población real. Único mismatch de nombres detectado: dataset de población usa "BOCA", barrios.csv usa "LA BOCA" (corregido a mano en `pipeline/ingest_poblacion.py`) |
| Población por comuna / por barrio | 15 comunas + 48 barrios | comuna es estimación 2017 (complementa NBI/hacinamiento, que no traía población total); barrio es censo 2010, mismo año que radios censales |
| Calles (callejero) | 31.961 tramos | trae jerarquía vial (troncal/distribuidora/local) y sentido de circulación; 1.729 tramos sin comuna asignada (autopistas/bordes). Columna "long" del origen es largo del tramo en metros, no longitud — ver nota en `pipeline/ingest_calles.py` |
| Accesos por autopista | 11 peajes/pórticos | AU Illia, Perito Moreno, Dellepiane, 25 de Mayo, Paseo del Bajo |
| Estadios | 30 | mismo sistema de coordenadas legacy que escuelas/hospitales |
| Eventos masivos | 2.898 permisos | 2019 + 2023-2026 (2020-2022 no publicados). Esquema distinto en cada archivo — ver notas de calidad abajo |
| Clima diario | 3.866 días (2016-01-01 a hoy) | NASA POWER, punto único (Obelisco) — no diferencia microclima entre barrios |

### Datos que se buscaron y no existen como abiertos

Cantidad de efectivos/oficiales, cantidad de móviles/patrullas disponibles, ubicación de radares móviles de velocidad, y la red completa de cámaras de seguridad urbana (más allá de las 224 de control vehicular) **no están publicados** — es información operativa de seguridad que el gobierno no divulga en detalle, tiene sentido que no exista. "Botones antipánico" sí existe pero es solo un total anual a nivel ciudad, sin geolocalización, no sirve para el modelo.

Nivel de ingreso y tasa de desempleo tampoco existen desglosados por comuna/barrio — solo hay totales a nivel ciudad por año (útiles para contexto, inútiles para diferenciar riesgo entre zonas). Se usan NBI y hacinamiento como proxies de vulnerabilidad socioeconómica en su lugar, que sí tienen ese desglose.

Series históricas diarias del Servicio Meteorológico Nacional **no son automatizables**: su único endpoint público estable solo da tiempo actual + pronóstico a 5 días, y la página de descarga de históricos está detrás de Cloudflare. Se usa NASA POWER como reemplazo (satelital, no estación puntual) — ver `pipeline/ingest_clima.py`.

Segmentación de población por edad/sexo **tampoco existe por zona**: el único dataset de estructura etaria de GCBA (`estructura-demografica/est_pob_sexo...`) es serie histórica 1855-presente a nivel ciudad completa, sin ningún desglose espacial — no sirve para diferenciar riesgo entre zonas y no se ingesta. Censo 2022 por radio tampoco está publicado en este portal (solo 2001 y 2010 a esa granularidad); si hace falta, habría que cruzar con el Portal Geoestadístico de INDEC, que usa otra cartografía/códigos.

### Lecciones de esta fase

Los datasets de transporte (EcoBici, Molinetes) cambiaron de esquema de columnas, delimitador, encoding o estructura de archivo **casi todos los años** — nada de esto está documentado en el portal de datos abiertos, se descubrió a fuerza de que el pipeline fallara con errores concretos. Cosas a tener en cuenta si se vuelve a correr la ingesta desde cero o se agregan años nuevos:

- Los scripts validan integridad de cada descarga (zip corrupto → se borra y re-descarga solo) porque el portal tiene caídas y timeouts de red frecuentes.
- No asumir que un ZIP tiene un solo archivo adentro — desde 2022 Molinetes viene partido en ~24-26 archivos por año.
- No asumir el mismo delimitador o encoding entre años de la misma fuente.
- Los joins por nombre de estación (texto libre) contra datasets de referencia nunca son 100% exactos — documentar el % sin matchear en vez de asumir cobertura total.
- **GCBA usa dos sistemas de coordenadas planas distintos entre datasets, sin documentarlo**: siniestros viales usa GKBA (Gauss-Krüger CABA 2019, oficial desde 2019), pero escuelas y hospitales todavía usan un sistema previo ("0 de Flores"). Aplicar la fórmula de uno al otro tira puntos a 90km de distancia sin ningún error visible en el código — solo se nota si se valida el rango de lat/lon contra los límites reales de la ciudad. Se calibraron ambos cruzando direcciones conocidas contra el geocodificador oficial de GCBA (`ws.usig.buenosaires.gob.ar`) en vez de confiar en el código EPSG que documenta el portal (9497), que ni siquiera existe en las bases de PROJ. Ver `pipeline/geo_utils.py`. Estadios (agregado después) también usa el sistema legacy, no el nuevo.
- El dataset de eventos masivos tiene **tres esquemas distintos en 5 archivos anuales** (2019 vs. 2023 vs. 2024-2026): cambia el delimitador, las columnas disponibles (barrio/aforo/lat-lon no están en todos) y hasta el encoding — el archivo 2023 es cp850 (DOS Latin US), el único de todo el proyecto que no es utf-8. Se detectó porque "Denominación" rompía el parser en utf-8 y en latin-1 daba un carácter distinto al esperado. Ver `pipeline/ingest_eventos_masivos.py`.
- No asumir que un nombre de columna es lo que parece: en el callejero, la columna "long" es el largo del tramo en metros, no longitud geográfica.

## Estado de Capa 0 (unificación espacio-temporal)

Grilla H3-8 generada sobre CABA (unión de los 48 barrios, no existe un dataset propio de "límite CABA"): **459 hexágonos** (`data/features/hex_maestra.parquet`), con `barrio_id`/`comuna_id` (point-in-polygon contra `barrios.parquet`) y `radio_censal_id` (contra `radios_censales.parquet`) por centroide. 58 hexágonos de borde/costa no caen dentro de ningún barrio (agua, terraplenes) — quedan sin `barrio_id`/`comuna_id`, es correcto que así sea.

`h3.polygon_to_cells` con el modo por default (`contain="center"`, solo hexágonos cuyo *centro* cae adentro del polígono) dejaba 1-6% de los puntos de delitos/siniestros/alumbrado fuera de la grilla — puntos reales de CABA cerca de la costa caían en hexágonos de borde cuyo centro quedaba just afuera. Se cambió a `polygon_to_cells_experimental(..., contain="overlap")` (cualquier hexágono que toque el polígono, aunque sea parcial) y el problema bajó a <0,5%.

Datasets ya cruzados con hex_id (`src/etl/assign_hex_puntual.py`, `assign_hex_calles.py`): delitos, siniestros_hechos, cámaras, alumbrado, cajeros, comisarías (ubicación puntual), escuelas, hospitales, universidades, estadios, ecobici/molinetes (estaciones), calles (por el punto medio del tramo, ya calculado en `pipeline/ingest_calles.py`), accesos_autopistas (+ tramo de calle troncal más cercano, reproyectado a EPSG:5347 para que la distancia sea en metros reales). Eventos masivos también pasó por el script pero solo 129 de 2.898 filas tienen hex_id (las de 2019, únicas con lat/lon) — el resto (2023-2026) solo tiene barrio, que es un tipo de cruce distinto (join por nombre, no point-in-hex), pendiente.

Pendiente, y son operaciones distintas a point-in-hex (no encajan en `asignar_hex_id`): **espacios_verdes** y **comisarias.parquet** (el de zonas de patrullaje) necesitan overlay de polígono contra la grilla (% de área, no un punto); **población por hex** (denominador per cápita) sale de prorratear `poblacion_comuna`/`poblacion_barrio` por área, aunque ya se puede aproximar sin prorratear porque `hex_maestra` ya tiene `radio_censal_id` — un join directo contra `radios_censales.poblacion_total` alcanza para una primera versión.

## Estado de Capa 1 v1 (modelo núcleo, sin exógenas)

`src/model_core/build_training_table.py` arma `data/features/training_table.parquet`: grano (hex_id, fecha, turno), 401 hexágonos × 3.653 días (2016-2025) × 4 turnos = 5.859.412 filas (907MB en memoria, 28MB en parquet). Target: conteo total de delitos (los 6 tipos juntos — desagregar por tipo multiplicaría la tabla ~6x, se deja para v2). Features: lags 7/30/365 días y rolling 7/30 días por hex×turno, vecindad espacial (anillos H3 k=1/k=2, sobre el `roll_30d` ya rezagado de cada vecino para no filtrar información futura — usar el conteo contemporáneo del vecino sería fuga de datos), NBI por radio censal, hacinamiento por comuna (no hay a nivel radio), población, cámaras y luminarias por hex, y calendario (día de semana, mes, feriado vía API de ArgentinaDatos).

`src/model_core/train_baseline.py` entrena LightGBM con objetivo Poisson, split temporal (train ≤2023, val 2024 para early stopping, test 2025). Resultado en test:

| | MAE | Recall@10% área | Recall@20% área | Recall@30% área |
|---|---|---|---|---|
| Modelo LightGBM | 0.290 | 27.7% | 45.4% | 58.5% |
| Baseline naive (promedio histórico hex×turno) | 0.296 | 27.4% | 44.7% | 58.4% |

**Lectura honesta**: el modelo le gana apenas al baseline naive. `hex_id` y `radio_censal_id` dominan la importancia de features por lejos — la mayor parte del "riesgo" que se captura es la heterogeneidad espacial pura (qué tan peligroso es el lugar en promedio), no la dinámica temporal (rachas, contagio espacial). Con una tasa media de 0,23 delitos por hex×turno y 82,8% de celdas en cero, tiene sentido: a esta resolución el proceso es casi estacionario por celda, así que un promedio histórico ya captura casi todo. Lo bueno: **hay concentración espacial real y se está capturando** (30% del área concentra 58% de los delitos, muy por encima de lo esperable si el riesgo fuera uniforme).

### v2 — exógenas (`src/model_core/agregar_exogenas.py`, `train_v2.py`)

Se sumó clima (join por fecha), flag de evento masivo (point-in-hex para 2019, join por barrio para 2023-2026) y cercanía a estadio (buffer 500m, reproyectado a EPSG:5347). **No mejoró nada** respecto a v1 — mismo MAE (0.291), mismo Recall@K exacto en cada umbral. `evento_en_hex` y `evento_en_barrio` tienen importancia **0** en el modelo (nunca se usaron en ningún split): a esta resolución (hex×día×turno) los eventos son demasiado raros — `evento_en_hex` es positivo en ~0,001% de las filas — para que haya señal aprendible. Clima aporta algo de importancia (`temp_media_c` por encima de varios lags) pero no alcanza a mover el Recall@K.

**Conclusión de v1 vs. v2**: el cuello de botella no son las exógenas, es que el proceso a este grano es casi puramente espacial. Antes de seguir sumando variables, tiene más sentido: (a) construir el Módulo A sobre lo que ya funciona (la concentración espacial), ya que no depende de mejorar la parte temporal, o (b) probar un grano temporal más agregado (semanal en vez de diario) donde la señal dinámica podría distinguirse mejor del ruido.

**Reentreno con los overlays de polígono** (`poblacion_hex`, `pct_espacio_verde`, `comisaria_id` de `src/etl/overlay_poligonos.py`, sumados a `build_training_table.py`): mismo resultado que v2 — MAE y Recall@K **idénticos** al modelo sin estas features (0.2902, 45.4%, 58.5%), y las tres quedan con importancia bajísima. Confirma el patrón: a esta resolución (hex×día×turno) el modelo ya captura "dónde es peligroso" a través de `hex_id`/`radio_censal_id`/historial — variables de contexto estático adicionales no aportan señal medible que esos features no capturen ya indirectamente.

**Grano semanal** (`build_training_table_semanal.py`, `train_semanal.py`): la hipótesis era que el conteo diario, muy disperso (82,8% ceros, media 0,23), enterraba señal dinámica que un grano más agregado podría revelar. Agregar por semana (401 hex × 523 semanas × 4 turnos = 838.892 filas) baja los ceros a 43,8% y sube la media a 1,59. Resultado matizado:

| | MAE vs. baseline naive | Recall@20% | Recall@30% |
|---|---|---|---|
| Diario | 0.2902 vs 0.2961 (mejora relativa 1,99%) | 45,4% | 58,5% |
| Semanal | 0.9239 vs 0.9510 (mejora relativa **2,85%**) | 45,5% | 58,6% |

El grano semanal le gana un poco más al baseline en error (MAE/RMSE), pero el **Recall@K —la métrica que más importa para priorizar zonas— queda prácticamente igual**. Conclusión: agregar por semana no cambia la historia de fondo, solo la afina levemente. La concentración espacial sigue siendo lo que carga el peso del modelo, con o sin más resolución temporal.

## Auditoría técnica externa y remediación P0

Un panel externo (ver artefacto publicado en la conversación) revisó las 16 dimensiones del proyecto contra el estado del arte de crime analytics/urban computing/investigación operativa. Dos hallazgos se marcaron **P0** (antes que cualquier otra mejora) y ya se resolvieron:

### PAI/PEI (`train_baseline.py::pai_pei`) — métricas estándar de la literatura

Recall@K es una métrica ad-hoc; **PAI (Predictive Accuracy Index) y PEI (Predictive Efficiency Index)** (Chainey, Tompson & Uhlig 2008) son el estándar de hotspot policing, lo que hace el resultado comparable contra papers publicados y no solo contra el propio baseline. Sobre test 2025:

| k | PAI (veces mejor que azar) | PEI (vs. techo con hindsight) |
|---|---|---|
| 10% | 2.77 | 99.3% |
| 20% | 2.27 | 99.4% |
| 30% | 1.95 | 99.6% |

PAI ~2-2.8x es un resultado sólido y comparable con literatura de otras ciudades. **PEI ~99% es el hallazgo más fuerte**: el modelo está a centésimas del techo teórico (el mejor mapa de hotspots posible con hindsight total) a esta resolución — no es que el modelo sea débil, es que a grano hex×día×turno casi no queda margen de mejora sin cambiar la resolución o el enfoque de fondo (coherente con todo lo demás: la heterogeneidad espacial ya se captura casi al máximo posible).

### Validación espacial (`src/validation/spatial_holdout.py`)

El documento de arquitectura original pedía "dejar afuera un subconjunto de hexágonos completos" y nunca se había hecho — todo el testing anterior usaba split temporal, que solo prueba interpolación en el tiempo sobre hexágonos ya vistos. Se reentrenó excluyendo 80 de 401 hexágonos (20%) **completamente** de train/val, y se comparó el test 2025 separado en vistos vs. holdout:

| | MAE | PAI@20% | PEI@20% |
|---|---|---|---|
| Hexágonos vistos en entrenamiento (321) | 0.283 | 2.23 | 99.6% |
| **Hexágonos holdout, nunca vistos (80)** | 0.325 | 2.31 | 98.2% |

**Resultado contrario a lo previsto en la auditoría**: dado que `hex_id` domina la importancia de features, se esperaba una degradación fuerte en hexágonos nunca vistos (el modelo "no puede haber memorizado" una categoría que no existía en train). En cambio, PAI/PEI se mantienen prácticamente iguales — el MAE sí empeora (+15% relativo), pero el ranking de riesgo (lo que importa para priorizar) generaliza bien. Lectura: el modelo no depende de memorizar `hex_id` en sí, sino que apoya la predicción de un hexágono nuevo en `radio_censal_id`/`comuna_id` (unidades espaciales más gruesas, parcialmente representadas en train por hexágonos vecinos del mismo radio/comuna) y en las features socioeconómicas/de infraestructura — es decir, sí generaliza a partir de estructura, no solo de identidad. Buena noticia, y una corrección honesta a la hipótesis planteada en la auditoría: no toda crítica plausible se confirma con el dato.

### Auditoría de equidad (`src/validation/auditoria_equidad.py`)

Limitación documentada explícitamente: el modelo aprende de delitos **denunciados**, no de delito real — si el patrullaje histórico ya estuvo sesgado hacia ciertas zonas, el riesgo "aprendido" puede formalizar ese sesgo en vez de medir riesgo genuino (Lum & Isaac 2016; Ensign et al. 2018, *Runaway Feedback Loops in Predictive Policing*). Este proyecto no tiene forma de medir "delito real" independiente del registro policial — no se puede resolver el problema de fondo con los datos disponibles, pero sí se puede chequear una pregunta operacionalizable: ¿el riesgo predicho correlaciona con NBI/hacinamiento **más de lo que el historial delictivo por sí solo explica**?

Correlación simple (15 comunas) entre `score_riesgo` medio y variable socioeconómica, y correlación parcial controlando por historial delictivo de la comuna en train:

| Variable | r simple | r parcial (controlando historial) |
|---|---|---|
| % hogares con NBI | 0.410 | 0.139 |
| % hacinamiento crítico | 0.047 | -0.279 |

La correlación con NBI cae fuerte (0.41→0.14) al controlar por historial — la mayor parte de esa relación es indirecta (comunas con más NBI ya tenían más historial delictivo, no es que el modelo use NBI como proxy de clase social por sí solo). Hacinamiento hace lo contrario (sube en magnitud y cambia de signo) — señal a vigilar, aunque con **n=15 comunas la correlación parcial tiene muy pocos grados de libertad**, no alcanza para una conclusión fuerte en ningún sentido. Esto no es una auditoría de sesgo policial resuelta — es el chequeo honesto de qué tan independiente es el score de la vulnerabilidad socioeconómica, documentado para que quien use el sistema sepa qué mide y qué no mide.

## P1 de la auditoría técnica

### POIs sensibles + flujo peatonal (`src/etl/agregar_poi_y_flujo.py`)

Escuelas, hospitales, universidades y cajeros (buffer 300m del centroide, no "mismo hex" — evita subestimar en los bordes) y flujo EcoBici/Molinetes por hex×turno (a diferencia de cámaras/alumbrado, que son estáticos, el flujo peatonal sí depende del turno). Estaban calculados desde Capa 0 / Módulo B pero nunca llegaban al modelo núcleo — cerraban la mitad de Crime Pattern Theory (nodes/paths) ausente del feature set.

**Cuarta vez que se repite el mismo patrón**: reentrenado con estas 6 features nuevas, MAE/Recall@K/PAI/PEI quedan **idénticos** a la versión anterior (0.2902, 45.4%, PEI 99.3-99.6%). `flujo_molinetes` y `flujo_ecobici` sí entran con más importancia que la mayoría de las socioeconómicas (163 y 157 respectivamente, por encima de `poblacion_hex`, NBI, hacinamiento), pero no mueven el agregado. Con v2 (exógenas), los overlays de polígono, y ahora POIs+flujo, van cuatro rondas de "sumar más contexto estático no mejora el ranking" — el hallazgo ya no es una casualidad de una corrida, es la conclusión estructural del proyecto: a este grano, el modelo está saturado en lo que la heterogeneidad espacial pura puede explicar, y hace falta un cambio de enfoque (no otra feature) para mover la aguja — exactamente lo que señala la auditoría técnica en la sección de simulación/decision intelligence, no en features adicionales.

### Sobredispersión e incertidumbre (`train_incertidumbre.py`)

La auditoría midió sobredispersión real en `conteo_delitos` (varianza/media = 1,59; Poisson asume 1,0) y señaló que el modelo nunca cuantifica incertidumbre — emite un solo número puntual para un sistema que alimenta asignación de recursos públicos.

**Tweedie vs. Poisson**: MAE 0,2900 vs. 0,2902, PAI/PEI iguales o levemente mejores (PEI 99,6-99,7% vs. 99,4-99,6%). Diferencia marginal en las métricas, pero es el objetivo estadísticamente correcto dado el `1,59` medido — **se adoptó como el objetivo de producción** en `train_baseline.py` (ver docstring del módulo), no por ganancia de métrica sino por corrección del supuesto de base.

**Regresión cuantílica (p10/p50/p90)**, misma tabla y split: cero *quantile crossing* (p10 nunca superó a p90, 0 de 585.460 filas), pero la cobertura empírica del intervalo [p10,p90] salió en **95,1%** contra un objetivo nominal de ~80% — los tres modelos de cuantiles se entrenan de forma independiente, sin restricción conjunta, y eso los deja sobre-calibrados (intervalos más anchos de lo que deberían). Queda documentado como limitación conocida: la corrección real es **conformal prediction** (garantías de cobertura finitas, model-agnostic — la recomendación original de la auditoría), no implementada todavía. Igual, la banda ya generada es un punto de partida utilizable: ancho medio 0,71 delitos esperados, algo más ancho en el cuartil de mayor riesgo predicho (0,88) que en los cuartiles medios — sensato, aunque no estrictamente monótono.

Modelos guardados: `modelo_nucleo_tweedie.txt` (el mismo que ahora es `modelo_nucleo_v1.txt` de producción), `modelo_nucleo_p10.txt`, `modelo_nucleo_p50.txt`, `modelo_nucleo_p90.txt` — los cuantiles quedan disponibles para optimización robusta en Módulo A (siguiente P1), no se usan todavía en `predecir_riesgo.py`.

`riesgo_predicho.parquet` ya se regeneró con el modelo Tweedie de producción (números marginalmente distintos a Poisson, la diferencia es mínima).

### Grafo vial real (`src/etl/build_grafo_vial.py`) — Módulo A y C

La auditoría señaló dos debilidades con la misma causa: Módulo A medía cobertura en línea recta sobre CRS métrico, Módulo C aproximaba el corredor de cada acceso con un buffer de radio fijo — ninguno de los dos usaba topología vial real. Se descargó el grafo vial real de CABA vía OSM/osmnx (**17.811 nodos, 37.036 tramos dirigidos** — dirigido, respeta sentido único nativamente, sin tener que leer `sentido` de `calles.parquet` a mano) y se cachea en `data/features/grafo_vial.graphml`.

**Módulo A, resultado grande**: cobertura por distancia de red real (Dijkstra de una sola fuente con corte, no línea recta):

| | Euclidiana (anterior) | Red real (actual) |
|---|---|---|
| Actual (75 comisarías) | 61.5% | **35.0%** |
| Optimizado, K=40 | 62.1% | **41.5%** |
| Ganancia | +0.6pp | **+6.5pp** |

Solo el 0,5% de los 190.876 pares (hexágono, candidato) cambia de estado individualmente al pasar de línea recta a calle real — pero alcanza para tumbar la cobertura agregada en más de 20 puntos, porque muchos hexágonos dependían de un único candidato "borderline" cuya distancia real supera los 800m aunque la línea recta no. **La cifra de cobertura actual de la sección de Módulo A más arriba (61,5%) estaba sobreestimada** — la real, con calles de verdad, es 35%. La ganancia relativa de optimizar (+6,5pp en vez de +0,6pp) es ahora más convincente, no menos: hay más margen real para mejorar del que el número euclidiano sugería.

**Módulo C**: el ranking de accesos cambia de forma no trivial al reemplazar el buffer por recorrido real del subgrafo de vías importantes (motorway/trunk/primary/secondary de OSM, análogo a troncal/distribuidora de GCBA). Alberti y Pórtico Independencia se mantienen 1° y 2° en ambas versiones (señal de robustez en los extremos), pero Dellepiane sube del puesto 7-8 al 3-4, Sarmiento sube del último puesto al 5°, y el grupo Illia baja del 3°-5° al 7°-9° — el buffer circular anterior sobre-representaba corredores que en la realidad no son alcanzables por vía importante en 2km reales, y sub-representaba otros conectados por una ruta más indirecta pero real.

Dashboard regenerado y redesplegado con estos números (auto-deploy vía GitHub — el push disparó el build solo, 15s, sin intervención manual).

## Motor de escenarios (`src/scenarios/motor_escenarios.py`)

Último ítem de P1 y la brecha más grande contra la visión del producto (auditoría, sección 8): el brief pedía responder "¿qué recursos deberían moverse?", "¿cuál sería el impacto?" y "¿qué pasaría si cambian las condiciones?" de forma interactiva — antes de esto, cada pregunta era editar una constante a mano en un script y volver a correrlo. No es un gemelo digital con simulación de agentes (fuera de alcance real para una persona en esta máquina) — es la ruta pragmática que señaló la auditoría: reutilizar Capa 1 + Módulo A detrás de una función de escenarios en vez de investigación nueva.

Dos tipos de escenario, porque responden preguntas distintas:

**Escenario de condiciones** (perturbar features estáticas de hexágonos puntuales, re-predecir con el modelo ya entrenado, sin reentrenar). Probado triplicando `n_luminarias` en los 5 hexágonos de mayor riesgo del turno Tarde:

```
Riesgo total ciudad: 157.71 -> 157.71 (+0.00%)
```

**Delta exactamente cero** en los 5 hexágonos. No es un bug del motor — es la confirmación, ahora en términos de "palanca de política concreta" en vez de importancia de feature abstracta, de algo que este proyecto viene midiendo desde v2: el modelo nunca aprendió sensibilidad real a `n_luminarias` (importancia de splits: 1, la más baja de toda la tabla — ver sección de Capa 1). El motor de escenarios funciona correctamente; lo que expone es un límite real del modelo, no un límite del motor.

**Escenario de recursos** (cambiar K_PATRULLAS o el radio de cobertura, re-resolver el MCLP de Módulo A sobre el mismo riesgo, comparar contra la cobertura actual). Curva completa, turno Tarde, radio 800m real:

| K patrullas | Cobertura | vs. actual (35,0%) |
|---|---|---|
| 20 | 26.7% | -8.3pp |
| 40 | 41.5% | +6.5pp |
| 60 | 52.2% | +17.2pp |

A diferencia de las condiciones estáticas, **esto sí responde con una señal clara y útil** — reasignar recursos (dónde están las patrullas) mueve la cobertura mucho más que cualquier intervención de infraestructura que el modelo haya aprendido a valorar. Es, en sí mismo, un hallazgo de producto: el apalancamiento real de este sistema está en la asignación de recursos (Módulo A/B), no en recomendar mejoras de infraestructura basadas en el modelo núcleo tal como está entrenado hoy.

**Limitación explícita, no resuelta**: el motor no responde "¿cómo evolucionará en las próximas horas?" — el modelo predice un patrón histórico promedio (2025), no una proyección desde "ahora"; eso requeriría infraestructura de forecasting en tiempo real (ingesta continua, ventana móvil), fuera de alcance de este P1.

## P2: tests de propiedad (`tests/`) — encontraron un bug real

Primer ítem de P2 (auditoría, sección 11): 18 tests con `pytest`, corren sobre los parquet ya generados (invariantes, no recomputan geopandas) más tests puros de lógica (`turno_desde_hora`, `pai_pei`). El test que la auditoría pidió textualmente — *"la suma de población por hex dentro de un barrio debe igualar la población del barrio"* — ya pasa (regresión del bug de `overlay_poligonos.py` ya corregido).

**Los tests de `turno_desde_hora` encontraron un bug nuevo, real, no relacionado con lo que motivó escribirlos**: `hex_utils.py` usaba `pd.cut(..., right=True)` (el default), que deja cada límite exacto de turno en el bucket ANTERIOR — hora 6 caía en "Madrugada" en vez de "Mañana", hora 14 en "Mañana" en vez de "Tarde", hora 22 en "Tarde" en vez de "Noche". Se corrigió con `right=False`.

**Impacto real medido**: `delitos.parquet` tiene franja en {6, 14, 22} en **167.901 de 1.353.136 filas (12,4%)** — todas mal clasificadas de turno hasta ahora. Esto es anterior a P0/P1, viene desde Capa 0 (`assign_hex_puntual.py`) y se propaga a `training_table.parquet`, el modelo, y `riesgo_predicho.parquet` por turno.

**Recascade completo ejecutado** (`assign_hex_puntual.py` → `agregar_poi_y_flujo.py` → `build_training_table.py` → reentrenar → `predecir_riesgo.py` → Módulo A/B/C → export dashboard → redeploy automático vía GitHub). El impacto agregado terminó siendo chico — consistente con todo lo demás en este proyecto, donde la heterogeneidad espacial domina por sobre el resto:

| | Antes del fix | Después |
|---|---|---|
| MAE modelo | 0.2900 | 0.2923 |
| Recall@30% | 58.6% | 58.6% |
| PEI@20% | 99.6% | 99.7% |
| Módulo A, actual (75 comisarías) | 35.0% | 35.1% |
| Módulo A, K=40 optimizado | 41.5% | 41.8% |
| Módulo B, cobertura | 24.9% | 25.0% |
| Módulo C, ranking de accesos | — | idéntico en orden |

**Nota de honestidad**: los scripts de diagnóstico que no forman parte de la cadena de producción (`train_v2.py`, `train_semanal.py`, `train_incertidumbre.py`, `spatial_holdout.py`, `auditoria_equidad.py`) no se re-corrieron con los datos corregidos — dado lo chico del impacto agregado medido arriba, sus conclusiones cualitativas (Tweedie ≈ Poisson, el modelo generaliza bien a hexágonos nuevos, NBI mayormente explicado por historial) casi seguro se sostienen, pero los números exactos que reportan quedan desactualizados hasta que se vuelvan a correr.

## P2: MLflow (`train_baseline.py`, `train_v2.py`, `train_semanal.py`)

Segundo ítem de P2 (auditoría, sección 10): cada corrida de entrenamiento ahora se registra en MLflow local (`mlflow.db`, backend SQLite — "cero infraestructura nueva" como pedía la auditoría, un solo archivo, sin server). `metricas()`, `recall_at_k()` y `reportar_pai_pei()` en `train_baseline.py` ahora devuelven valores además de imprimir, así se pueden loguear sin recalcular. `mlflow ui --backend-store-uri sqlite:///mlflow.db` levanta el dashboard de comparación de corridas.

Verificado funcionando de punta a punta en `train_baseline.py` (el modelo de producción — params, métricas modelo/naive, y el `.txt` del modelo como artifact, todo quedó en la corrida `v1-tweedie`).

**Límite real encontrado, no forzado**: al intentar refrescar `train_v2.py`/`train_semanal.py` con los datos post-fix de turno, `agregar_exogenas.py` tiró `numpy._core._exceptions._ArrayMemoryError` reconstruyendo `training_table_v2.parquet` (dos veces, en dos operaciones distintas de pandas) — la máquina de 3,4GB de RAM se quedó sin memoria real después de una sesión larga con muchos procesos pesados encadenados. No es un bug de código: es exactamente la restricción que la auditoría técnica nombra en su sección 13 ("La restricción real: 3,4GB de RAM"). El código de tracking de MLflow quedó agregado a ambos scripts y es correcto (mismo patrón que `train_baseline.py`, ya verificado), pero `training_table_v2.parquet`/`training_table_semanal.parquet` siguen reflejando datos de antes del fix de turno hasta que se puedan reconstruir con memoria disponible — idealmente en una sesión nueva, no al final de una ya muy larga.

## Módulo A — Asignación de patrullas (`src/optimization/modulo_a_patrullas.py`)

Maximal Covering Location Problem resuelto con `pulp` (programación lineal entera, no ML) sobre `riesgo_predicho.parquet` (score de riesgo por hex×turno del modelo v1, generado por `predecir_riesgo.py`, promediado sobre 2025). Candidatos: las 75 comisarías reales + los 401 centroides de hexágonos. Radio de cobertura 800m. Restricción: ninguna comuna queda con cobertura cero.

Turno Tarde (el de mayor riesgo promedio):

| Escenario | Riesgo cubierto |
|---|---|
| Actual — 75 comisarías reales, tal como están | 61.5% |
| Optimizado, K=20 patrullas | 40.8% |
| Optimizado, K=40 patrullas | 62.1% |
| **Optimizado, K=75** (mismo presupuesto que hoy) | **84.4%** |

El dato que importa para el pitch: **a igual cantidad de unidades (75), solo cambiando dónde se ubican, la cobertura sube de 61.5% a 84.4%** — la infraestructura actual de comisarías no está posicionada donde el riesgo se concentra hoy. `K_PATRULLAS` y `TURNO` son parámetros al inicio del script (pensados como los sliders de un dashboard futuro).

## Módulo B — Ubicación de cámaras nuevas (`src/optimization/modulo_b_camaras.py`)

Weighted Max Coverage resuelto greedy (no MILP — el documento pide un ranking por ganancia marginal, que es justo lo que da el algoritmo greedy clásico). Peso por hexágono = riesgo (promedio de turnos) × boost por baja densidad de alumbrado × boost por alto flujo peatonal (ecobici + molinetes, combinados por percentil porque las escalas no son comparables) × descuento si ya está cubierto por una cámara existente. Candidatos: hexágonos a más de 100m de una cámara actual (224 cámaras reales).

Con `N_CAMARAS_NUEVAS=30` y radio de cobertura 150m: **cubren 24.9% del riesgo ponderado total** que hoy no está cerca de ninguna cámara. Solo 18 de 401 hexágonos caían dentro del radio de una cámara existente antes de correr esto — la cobertura actual de cámaras es baja en términos relativos al área de la ciudad.

## Módulo C — Controles de acceso (`src/optimization/modulo_c_controles.py`)

A diferencia de A y B, no trabaja sobre hexágonos sueltos sino sobre el grafo vial. **Simplificación importante**: el documento pide "recorrer los tramos troncales/distribuidores" desde cada acceso, lo que requiere topología real de calles (qué tramo conecta con cuál) — `calles.parquet` son geometrías sueltas sin esa topología armada. Se aproxima el "corredor" como los tramos de jerarquía troncal/distribuidora principal dentro de un radio fijo (`RADIO_CORREDOR_M=2000`) del acceso, en vez de navegar el grafo real. Mismo espíritu, menor costo de implementación — si hace falta más precisión, este es el punto a mejorar primero.

Ranking de los 11 accesos/pórticos por score combinado (percentil de accidentalidad histórica + percentil de riesgo delictivo del corredor):

| # | Acceso | Autopista | Siniestros en corredor | Score |
|---|---|---|---|---|
| 1 | Alberti | AU 1 – 25 de Mayo | 9.164 | 0.95 |
| 2 | Pórtico Independencia | Au Paseo del Bajo | 6.188 | 0.95 |
| 3 | Pórtico Illia al Norte/Sur, Illia | AU Illia | 3.185 | 0.59 |

El corredor de **25 de Mayo/Paseo del Bajo** concentra la mayor accidentalidad histórica de lejos — son las autopistas más troncales del microcentro, tiene sentido que salga primero.

## Capa 3 — Validación y explicabilidad (`src/validation/`)

**SHAP** (`shap_explicabilidad.py`) matiza la lectura de Capa 1: la importancia por cantidad de *splits* de LightGBM decía que casi todo era `hex_id`. SHAP (que mide aporte real a la magnitud de la predicción, no cuántas veces se usa una feature) da otra foto:

| Feature | Aporte SHAP |
|---|---|
| roll_30d_sum (historial 30 días, mismo hex) | 29.3% |
| hex_id (ubicación) | 25.4% |
| vecino_k1_roll30 + vecino_k2_roll30 (contagio espacial) | 25.4% |
| turno + radio_censal_id + resto | ~20% |

Historial reciente + vecindad espacial suman **~56%**, más que la ubicación sola — la dinámica temporal sí aporta, solo que no se notaba contando splits. Explicaciones locales (top 5 hex×turno de mayor riesgo del test) siguen el mismo patrón: 40-50% del riesgo de cada predicción se explica por `roll_30d_sum`.

**Backtesting narrado + evolución mensual + calibración** (`backtesting_narrado.py`), sobre test 2025:

- Junio 2025: 9.783 delitos reales vs. 10.085 predichos por el modelo (suma sobre todos los hex×turno) — muy cerca. El top 20% de hexágonos marcados como más riesgosos concentró el 46.9% de los delitos reales del mes.
- **Recall@20% estable los 12 meses**: entre 44.1% y 47.1%, desvío de 1.3 puntos — no es una racha de un mes.
- **Calibración casi perfecta por decil**: en el decil de mayor riesgo, predicho=0.828 vs. real=0.821; en todos los deciles el promedio predicho y el real están a menos de un 3% de diferencia. El score no es solo bueno para *rankear* hexágonos, es confiable en términos absolutos.

Esto es más vendible que el resultado de Capa 1 solo: aunque el modelo apenas le gana al baseline naive en MAE, **está bien calibrado y es estable en el tiempo** — dos propiedades necesarias para que un organismo de gobierno confíe en el score.

## Export + Dashboard (`src/export/`, `dashboard/`)

Última etapa del roadmap. `src/export/generar_export.py` convierte los parquet de Capa 0-3 en JSON/GeoJSON livianos (~290KB en total) en `dashboard/public/data/`: `hex_riesgo.geojson` (459 hexágonos con riesgo por turno), `modulo_a/b/c.json`, `comisarias.geojson`, `camaras.geojson`, `metricas.json`. El dashboard nunca lee los parquet directo — todo pasa por este export para no acoplar el frontend al esquema de Python.

`dashboard/` es un proyecto Next.js 16 + React 19 + TypeScript + Tailwind v4, en el mismo repo (no separado — ver decisión más arriba). Mapa con **MapLibre GL** (sin API key, basemap oscuro de CARTO) coloreado por una rampa secuencial azul validada con la skill de dataviz (cuantiles, no escala lineal — el riesgo está muy sesgado). Panel lateral con toggles de capas (Módulo A/B/C, comisarías/cámaras reales) y panel de métricas (calibración, evolución mensual, cobertura de Módulo A) con gráficos SVG hechos a mano siguiendo los mark specs de la skill (líneas finas, tooltips on-hover, un eje por gráfico).

**Gotchas de esta etapa**:
- MapLibre GL v6 cambió a exports nombrados únicamente (`import { Map, NavigationControl, Popup } from "maplibre-gl"`) — el patrón viejo `import maplibregl from "maplibre-gl"` con default export ya no existe.
- `create-next-app` no scaffoldea sobre un directorio con archivos (el `public/data/` ya generado por el export) — hubo que crear en un directorio temporal y mergear.
- No se pudo verificar visualmente con la herramienta de automatización de navegador (el Chrome que controla la extensión no llega a `localhost:3000` aunque el servidor responde bien por `curl`/PowerShell en esta misma máquina — aislamiento de red entre la extensión y este entorno). Se verificó con `npm run build` + `npm run lint` (ambos limpios) y **a ojo por el usuario en su propio navegador — confirmado, el mapa renderiza bien**.

Gotchas encontrados: `siniestros_hechos` guarda lat/lon como texto, no float (se castea en `hex_utils.asignar_hex_id`); `hora_siniestro` viene como "HH:MM:SS" mientras que `franja` de delitos ya es un número 0-23 (se resuelve en `hex_utils.turno_desde_hora`, detecta el formato).

### Overlay de polígono (`src/etl/overlay_poligonos.py`)

Cierra los 3 cruces de la tabla que no son point-in-hex: `espacios_verdes` (% de área verde por hex — overlay real, 372 de 401 hex tienen algo de verde, media 7,1%), `comisarias` (qué comisaría de patrullaje cubre la mayor parte de cada hex — por área de intersección, no por centroide; los 401 hex quedaron cubiertos) y **población por hex**, prorrateada por área dentro del barrio ya asignado (no hace falta overlay hex-contra-barrio real: como los hexágonos H3-8 tienen área casi idéntica entre sí, prorratear por área da resultados casi uniformes dentro de cada barrio — verificado, la suma total coincide exacto con `poblacion_barrio` real: 2.890.151).

**Bug real encontrado y corregido**: la primera versión calculaba el denominador de la proporción (`area_total_por_barrio`, vía `groupby().transform("sum")`) *antes* de un `.merge()`, y lo reusaba después. `merge()` devuelve un DataFrame con índice nuevo (0..n-1) que no respeta el orden de filas original — pandas alinea operaciones aritméticas por índice, no por posición, así que la división terminó emparejando cada hex con el denominador de OTRO hex, silenciosamente (sin error, sin warning). El síntoma: la población total sumaba 3.478.949 en vez de 2.890.151, un 20% de más, y decenas de miles de más/de menos por barrio sin patrón obvio. Se corrigió haciendo todo el cálculo — merge y transform — sobre el mismo dataframe sin cortes en el medio. Regla general: nunca guardar el resultado de un `groupby().transform()` para usarlo después de un `merge()`/`sort`/cualquier operación que pueda reindexar.
